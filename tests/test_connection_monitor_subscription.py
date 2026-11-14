"""Subscription order, content identity, native payload and protocol presentation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.connection_monitor_config import MonitorBinding, build_monitor_config
from app.services.connection_monitor_native import protocol_details, validate_subscription_outbound
from app.services.connection_monitor_subscription import plan_monitor_configs, subscription_entries
from app.services.connection_monitor_types import MonitorConfigError, MonitorIssue


@pytest.fixture
def configs() -> list[dict]:
    fixture = json.loads((Path(__file__).parent / "fixtures/connection_monitor_catalog.json").read_text())
    return fixture["native_configs"]


def test_native_order_names_and_addresses_are_preserved_without_host_expansion(configs: list[dict]) -> None:
    configs.reverse()
    entries = subscription_entries(configs)
    assert [entry.name for entry in entries] == ["نام متغیر 2", "نام متغیر 1"]
    assert [entry.position for entry in entries] == [0, 1]
    plans = plan_monitor_configs(native_configs=configs, selected_keys=tuple(entry.config_key for entry in entries), account_revision="one")
    assert [len(plan.endpoints) for plan in plans] == [1, 1]
    core = build_monitor_config(tuple(MonitorBinding(plan.endpoints[0], 18080 + index) for index, plan in enumerate(plans)))
    for native, actual in zip(configs, core["outbounds"][1:]):
        actual["tag"] = native["outbounds"][0]["tag"]
        assert actual == native["outbounds"][0]


def test_reorder_does_not_change_saved_selection_and_changed_payload_is_not_substituted(configs: list[dict]) -> None:
    key = subscription_entries(configs)[0].config_key
    before = plan_monitor_configs(native_configs=configs, selected_keys=(key,), account_revision="one")
    configs.reverse()
    assert plan_monitor_configs(native_configs=configs, selected_keys=(key,), account_revision="one") == before
    configs[1]["outbounds"][0]["settings"]["vnext"][0]["address"] = "different.example"
    result = plan_monitor_configs(native_configs=configs, selected_keys=(key,), account_revision="one")[0]
    assert result.issue == MonitorIssue.CONFIG_UNAVAILABLE and not result.endpoints


def test_duplicate_labels_and_identical_configs_remain_distinct(configs: list[dict]) -> None:
    configs[1]["remarks"] = configs[0]["remarks"]
    configs.append(copy.deepcopy(configs[0]))
    entries = subscription_entries(configs)
    assert len({entry.config_key for entry in entries}) == 3
    assert [entry.name for entry in entries] == ["نام متغیر 1"] * 3


def test_account_revision_invalidates_measurement_without_retargeting(configs: list[dict]) -> None:
    key = subscription_entries(configs)[0].config_key
    first = plan_monitor_configs(native_configs=configs, selected_keys=(key,), account_revision="one")[0].endpoints[0]
    second = plan_monitor_configs(native_configs=configs, selected_keys=(key,), account_revision="two")[0].endpoints[0]
    assert first.endpoint_key == second.endpoint_key
    assert first.generation != second.generation


@pytest.mark.parametrize("protocol", ["vless", "vmess", "trojan", "shadowsocks"])
def test_native_proxy_protocol_fields_are_preserved(configs: list[dict], protocol: str) -> None:
    outbound = copy.deepcopy(configs[0]["outbounds"][0])
    outbound["protocol"] = protocol
    if protocol in {"trojan", "shadowsocks"}:
        outbound["settings"] = {"servers": [{"address": "proxy.example", "port": 443, "password": "synthetic-only", "method": "chacha20-ietf-poly1305"}]}
        outbound.pop("streamSettings")
    if protocol == "vmess":
        outbound["settings"]["vnext"][0]["users"] = [{"id": "11111111-1111-4111-8111-111111111111", "security": "auto"}]
    assert validate_subscription_outbound(outbound) == outbound
    details = protocol_details(outbound)
    assert details.protocol == protocol and details.transport == "tcp"
    if protocol == "shadowsocks":
        assert details.security == ""


def test_xhttp_tls_details_and_extra_fields_are_preserved_exactly(configs: list[dict]) -> None:
    outbound = configs[1]["outbounds"][0]
    stream = outbound["streamSettings"]
    stream["network"] = "xhttp"
    del stream["wsSettings"]
    stream["xhttpSettings"] = {"host": "cdn.example", "path": "/upload", "mode": "auto", "extra": {"scMaxEachPostBytes": 1000000}}
    stream["tlsSettings"]["echConfigList"] = ""
    assert validate_subscription_outbound(outbound) == outbound
    details = protocol_details(outbound)
    assert (details.protocol, details.transport, details.security, details.port) == ("vless", "xhttp", "tls", 8443)


@pytest.mark.parametrize("field,value", [
    ("protocol", "freedom"), ("proxySettings", {"tag": "direct"}), ("sendThrough", "127.0.0.1"),
])
def test_unsafe_native_routes_remain_visible_but_cannot_be_selected(configs: list[dict], field: str, value: object) -> None:
    configs[0]["outbounds"][0][field] = value
    entries = subscription_entries(configs)
    assert len(entries) == 2 and entries[0].issue == MonitorIssue.UNSUPPORTED
    plan = plan_monitor_configs(native_configs=configs, selected_keys=(entries[0].config_key,), account_revision="one")[0]
    assert not plan.endpoints and plan.issue == MonitorIssue.UNSUPPORTED


@pytest.mark.parametrize("key,value", [
    ("sockopt", {"dialerProxy": "direct"}), ("tlsSettings", {"certificateFile": "/private/key"}),
    ("tlsSettings", {"allowInsecure": True}), ("security", []), ("network", {}),
])
def test_native_dependencies_local_files_and_invalid_types_are_rejected_safely(configs: list[dict], key: str, value: object) -> None:
    outbound = configs[1]["outbounds"][0]
    outbound["streamSettings"][key] = value
    with pytest.raises(MonitorConfigError):
        validate_subscription_outbound(outbound)


@pytest.mark.parametrize("port", [True, 0, -1, 65536, 443.0, "443"])
def test_native_ports_are_strictly_validated(configs: list[dict], port: object) -> None:
    outbound = configs[0]["outbounds"][0]
    outbound["settings"]["vnext"][0]["port"] = port
    with pytest.raises(MonitorConfigError):
        validate_subscription_outbound(outbound)


def test_bounded_selection_never_returns_partial_capacity_success(configs: list[dict]) -> None:
    configs *= 7
    keys = tuple(entry.config_key for entry in subscription_entries(configs))
    with pytest.raises(MonitorConfigError, match="^endpoint_capacity$"):
        plan_monitor_configs(native_configs=configs, selected_keys=keys, account_revision="one")
    assert len(plan_monitor_configs(native_configs=configs, selected_keys=keys[:12], account_revision="one")) == 12


@pytest.mark.parametrize("payload", [None, {}, [None], [{}], [{"outbounds": []}], [{"outbounds": [None]}]])
def test_malformed_subscription_is_rejected_without_payload_details(payload: object) -> None:
    with pytest.raises(MonitorConfigError, match="^invalid_catalog$"):
        subscription_entries(payload)


def test_safe_representations_and_output_copies_hide_credentials(configs: list[dict]) -> None:
    entries = subscription_entries(configs)
    plans = plan_monitor_configs(native_configs=configs, selected_keys=(entries[0].config_key,), account_revision="one")
    secret = configs[0]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"]
    assert secret not in repr(entries) + repr(plans)
    plans[0].endpoints[0].outbound()["settings"].clear()
    assert plans[0].endpoints[0].outbound() == configs[0]["outbounds"][0]
