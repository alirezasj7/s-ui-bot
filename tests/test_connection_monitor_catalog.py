"""Offline host identity, full coverage and scope regression tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.connection_monitor_catalog import plan_monitor_hosts
from app.services.connection_monitor_types import MonitorConfigError, MonitorHostPlan, MonitorIssue


@pytest.fixture
def catalog() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "connection_monitor_catalog.json"
    return json.loads(path.read_text())


def plan(catalog: dict[str, Any], *, selected_ids: tuple[int, ...] = (41, 72),
         staff: dict[str, Any] | None = None, revision: str = "account-1") -> tuple[MonitorHostPlan, ...]:
    return plan_monitor_hosts(**catalog, selected_ids=selected_ids,
                              staff=staff if staff is not None else {"pg_is_owner": True},
                              account_revision=revision)


def test_every_static_address_gets_a_separate_stable_route(catalog: dict[str, Any]) -> None:
    plans = plan(catalog)
    assert all(item.is_ready for item in plans)
    assert [len(item.endpoints) for item in plans] == [2, 1]
    addresses = [endpoint.outbound()["settings"]["vnext"][0]["address"] for endpoint in plans[0].endpoints]
    assert addresses == ["edge-a.example", "edge-b.example"]
    assert len({endpoint.endpoint_key for item in plans for endpoint in item.endpoints}) == 3


def test_order_remarks_and_sampled_address_do_not_change_identity(catalog: dict[str, Any]) -> None:
    original = plan(catalog)
    catalog["hosts"].reverse()
    catalog["inbounds"].reverse()
    catalog["native_configs"].reverse()
    catalog["native_configs"][1]["outbounds"][0]["settings"]["vnext"][0]["address"] = "edge-a.example"
    for host in catalog["hosts"]:
        host["remark"] = "changed label"
        host["address"].reverse()
    assert plan(catalog) == original


def test_different_account_invalidates_samples_without_changing_endpoint_identity(catalog: dict[str, Any]) -> None:
    old, new = plan(catalog)[0].endpoints, plan(catalog, revision="account-2")[0].endpoints
    assert [item.endpoint_key for item in old] == [item.endpoint_key for item in new]
    assert all(first.generation != second.generation for first, second in zip(old, new))


def test_inbound_change_invalidates_generation(catalog: dict[str, Any]) -> None:
    original = plan(catalog)[0]
    catalog["hosts"][0]["inbound_tag"] = "new-tag"
    catalog["inbounds"][0]["tag"] = "new-tag"
    changed = plan(catalog)[0]
    assert changed.is_ready
    assert changed.endpoints[0].generation != original.endpoints[0].generation


def test_duplicate_native_samples_are_idempotent(catalog: dict[str, Any]) -> None:
    original = plan(catalog)
    catalog["native_configs"].append(copy.deepcopy(catalog["native_configs"][0]))
    assert plan(catalog) == original


def test_unselected_duplicate_host_still_makes_mapping_ambiguous(catalog: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(catalog["hosts"][0])
    duplicate["id"] = 99
    catalog["hosts"].append(duplicate)
    assert plan(catalog, selected_ids=(41,))[0].issue == MonitorIssue.AMBIGUOUS


def test_overlapping_expanded_address_cannot_hide_a_second_host(catalog: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(catalog["hosts"][0])
    duplicate.update(id=99, address=["edge-a.example"])
    catalog["hosts"].append(duplicate)
    assert plan(catalog, selected_ids=(41,))[0].issue == MonitorIssue.AMBIGUOUS


def test_conflicting_native_credentials_do_not_choose_the_first_config(catalog: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(catalog["native_configs"][0])
    duplicate["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"] = "22222222-2222-4222-8222-222222222222"
    catalog["native_configs"].append(duplicate)
    assert plan(catalog)[0].issue == MonitorIssue.AMBIGUOUS


@pytest.mark.parametrize("staff,allowed", [
    ({"pg_is_owner": True}, True),
    ({"pg_is_owner": False, "pg_admin_username": "monitor-owner"}, True),
    ({"pg_is_owner": False, "pg_admin_username": "other-shop"}, False),
    ({"role": "admin"}, False),
    ({}, False),
])
def test_catalog_scope_does_not_infer_owner_from_role(catalog: dict[str, Any], staff: dict[str, Any], allowed: bool) -> None:
    result = plan(catalog, staff=staff)[0]
    assert result.is_ready == allowed
    if not allowed:
        assert result.issue == MonitorIssue.OUT_OF_SCOPE


def test_unknown_ownership_is_not_proven_by_a_shared_catalog(catalog: dict[str, Any]) -> None:
    catalog["hosts"][0].pop("admin")
    assert plan(catalog, staff={"pg_admin_username": "monitor-owner"})[0].issue == MonitorIssue.OUT_OF_SCOPE


@pytest.mark.parametrize("change", ["disabled", "deleted", "missing_route", "missing_inbound"])
def test_unavailable_host_never_has_a_partial_plan(catalog: dict[str, Any], change: str) -> None:
    expected = MonitorIssue.MISSING_ROUTE
    if change == "disabled":
        catalog["hosts"][0]["is_disabled"] = True
        expected = MonitorIssue.HOST_UNAVAILABLE
    elif change == "deleted":
        catalog["hosts"].pop(0)
        expected = MonitorIssue.HOST_UNAVAILABLE
    elif change == "missing_route":
        catalog["native_configs"].pop(0)
    else:
        catalog["inbounds"].pop(0)
    result = plan(catalog)[0]
    assert result.issue == expected
    assert not result.endpoints


@pytest.mark.parametrize("field,value", [
    ("fragment_settings", {"xray": {"packets": "tlshello"}}),
    ("noise_settings", {"xray": [{"type": "rand"}]}),
    ("subscription_templates", {"xray": "custom"}),
    ("transport_settings", {"xhttp_settings": {"mode": "auto"}}),
    ("random_user_agent", True), ("use_sni_as_host", True), ("vless_route", "abcd"),
    ("allowinsecure", True), ("sni", []), ("sni", ["a.example", "b.example"]),
    ("port", None), ("new_client_option", "unknown"),
])
def test_unproven_host_settings_are_explicitly_not_ready(catalog: dict[str, Any], field: str, value: object) -> None:
    catalog["hosts"][0][field] = value
    assert plan(catalog)[0].issue == MonitorIssue.UNSUPPORTED


@pytest.mark.parametrize("field,value", [("port", True), ("port", 0), ("port", 65536), ("id", True)])
def test_malformed_catalog_is_rejected_safely(catalog: dict[str, Any], field: str, value: object) -> None:
    catalog["hosts"][0][field] = value
    with pytest.raises(MonitorConfigError, match="^invalid_catalog$"):
        plan(catalog)


@pytest.mark.parametrize("field,value", [("address", ["{SERVER_IP}"]), ("sni", ["*.example"])])
def test_dynamic_host_values_are_not_ready(catalog: dict[str, Any], field: str, value: object) -> None:
    catalog["hosts"][0][field] = value
    assert plan(catalog)[0].issue == MonitorIssue.UNSUPPORTED


def test_disabled_duplicate_host_does_not_make_a_route_ambiguous(catalog: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(catalog["hosts"][0])
    duplicate.update(id=99, is_disabled=True)
    catalog["hosts"].append(duplicate)
    assert plan(catalog)[0].is_ready


def test_unselected_unsupported_host_does_not_break_other_transports(catalog: dict[str, Any]) -> None:
    catalog["hosts"].append({"id": 99, "inbound_tag": "vmess", "address": []})
    catalog["inbounds"].append({"tag": "vmess", "protocol": "vmess", "network": "tcp"})
    assert all(item.is_ready for item in plan(catalog))
    assert plan(catalog, selected_ids=(99,))[0].issue == MonitorIssue.UNSUPPORTED


def test_unselected_dynamic_contender_is_not_silently_ignored(catalog: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(catalog["hosts"][0])
    duplicate.update(id=99, address=["{SERVER_IP}"])
    catalog["hosts"].append(duplicate)
    assert plan(catalog)[0].issue == MonitorIssue.AMBIGUOUS


@pytest.mark.parametrize("selected", [(True,), (0,), (-1,), (2147483648,), ("41",)])
def test_invalid_selected_identifiers_are_rejected(catalog: dict[str, Any], selected: tuple[int, ...]) -> None:
    with pytest.raises(MonitorConfigError, match="^invalid_catalog$"):
        plan(catalog, selected_ids=selected)


def test_duplicate_identity_in_catalog_is_rejected(catalog: dict[str, Any]) -> None:
    catalog["inbounds"].append(copy.deepcopy(catalog["inbounds"][0]))
    with pytest.raises(MonitorConfigError, match="^invalid_catalog$"):
        plan(catalog)


def test_capacity_counts_addresses_and_returns_no_partial_success(catalog: dict[str, Any]) -> None:
    catalog["hosts"][0]["address"] = [f"edge-{index}.example" for index in range(12)]
    catalog["native_configs"][0]["outbounds"][0]["settings"]["vnext"][0]["address"] = "edge-0.example"
    assert all(item.issue == MonitorIssue.CAPACITY and not item.endpoints for item in plan(catalog))
    assert len(plan(catalog, selected_ids=(41,))[0].endpoints) == 12


def test_endpoint_repr_and_safe_errors_do_not_reveal_account_credentials(catalog: dict[str, Any]) -> None:
    result = plan(catalog)
    secret = catalog["native_configs"][0]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"]
    assert secret not in repr(result)
    result[0].endpoints[0].outbound()["settings"].clear()
    assert plan(catalog) == result
