"""The generated core config can only relay through validated selected routes."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.connection_monitor_catalog import plan_monitor_hosts
from app.services.connection_monitor_config import MonitorBinding, build_monitor_config
from app.services.connection_monitor_types import MonitorConfigError
from app.services.connection_monitor_validation import validate_native_outbound
from app.services.connection_monitor_native import validate_subscription_outbound


@pytest.fixture
def catalog() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "fixtures" / "connection_monitor_catalog.json").read_text())


def test_input_routes_are_isolated_and_unmatched_traffic_is_denied(catalog: dict[str, Any]) -> None:
    plans = plan_monitor_hosts(**catalog, selected_ids=(41, 72), staff={"pg_is_owner": True}, account_revision="one")
    endpoints = tuple(endpoint for plan in plans for endpoint in plan.endpoints)
    config = build_monitor_config(tuple(MonitorBinding(endpoint, 18080 + index) for index, endpoint in enumerate(endpoints)))
    assert config["outbounds"][0]["protocol"] == "blackhole"
    assert {outbound["protocol"] for outbound in config["outbounds"]} == {"vless", "blackhole"}
    for inbound, rule, outbound in zip(config["inbounds"], config["routing"]["rules"], config["outbounds"][1:]):
        assert inbound["listen"] == "127.0.0.1"
        assert inbound["protocol"] == "http"
        assert rule["inboundTag"] == [inbound["tag"]]
        assert rule["outboundTag"] == outbound["tag"]
    assert config["log"]["loglevel"] == "none"


def test_reality_and_websocket_security_are_preserved(catalog: dict[str, Any]) -> None:
    for native in catalog["native_configs"]:
        original = native["outbounds"][0]
        route = validate_native_outbound(original).config()
        expected_server = copy.deepcopy(original["settings"]["vnext"][0])
        expected_server["users"][0].setdefault("flow", "")
        assert route["settings"]["vnext"] == [expected_server]
        for key, value in original["streamSettings"].items():
            for nested_key, nested_value in value.items() if isinstance(value, dict) else []:
                assert route["streamSettings"][key][nested_key] == nested_value
            if not isinstance(value, dict):
                assert route["streamSettings"][key] == value


def test_native_outbound_is_preserved_without_inserting_defaults(catalog: dict[str, Any]) -> None:
    for native in catalog["native_configs"]:
        original = native["outbounds"][0]
        assert validate_subscription_outbound(original) == original


@pytest.mark.parametrize("field,value", [
    ("proxySettings", {"tag": "direct"}), ("mux", {"enabled": True}),
    ("sendThrough", "127.0.0.1"), ("protocol", "freedom"), ("tag", "direct"),
])
def test_unsafe_or_unproven_outbound_settings_are_rejected(catalog: dict[str, Any], field: str, value: object) -> None:
    outbound = catalog["native_configs"][0]["outbounds"][0]
    outbound[field] = value
    with pytest.raises(MonitorConfigError, match="^unsupported_route$"):
        validate_native_outbound(outbound)


@pytest.mark.parametrize("field,value", [
    ("sockopt", {"dialerProxy": "direct"}), ("finalmask", {"tcp": []}),
    ("network", "xhttp"), ("security", "none"), ("tlsSettings", {"serverName": "cover.example"}),
])
def test_auxiliary_routes_and_unsupported_transports_cannot_be_silently_stripped(catalog: dict[str, Any], field: str, value: object) -> None:
    outbound = catalog["native_configs"][0]["outbounds"][0]
    outbound["streamSettings"][field] = value
    with pytest.raises(MonitorConfigError):
        validate_native_outbound(outbound)


@pytest.mark.parametrize("value", [True, 0, 1, "false"])
def test_certificate_verification_is_a_strict_boolean(catalog: dict[str, Any], value: object) -> None:
    outbound = catalog["native_configs"][1]["outbounds"][0]
    outbound["streamSettings"]["tlsSettings"]["allowInsecure"] = value
    with pytest.raises(MonitorConfigError):
        validate_native_outbound(outbound)


@pytest.mark.parametrize("port", [True, 0, -1, 65536, 18080.0])
def test_proxy_binding_port_has_strict_bounds(catalog: dict[str, Any], port: int) -> None:
    endpoint = plan_monitor_hosts(**catalog, selected_ids=(41,), staff={"pg_is_owner": True}, account_revision="one")[0].endpoints[0]
    with pytest.raises(MonitorConfigError):
        build_monitor_config((MonitorBinding(endpoint, port),))


def test_repeated_port_or_endpoint_is_rejected(catalog: dict[str, Any]) -> None:
    endpoints = plan_monitor_hosts(**catalog, selected_ids=(41,), staff={"pg_is_owner": True}, account_revision="one")[0].endpoints
    for bindings in ((MonitorBinding(endpoints[0], 18080), MonitorBinding(endpoints[1], 18080)),
                     (MonitorBinding(endpoints[0], 18080), MonitorBinding(endpoints[0], 18081))):
        with pytest.raises(MonitorConfigError):
            build_monitor_config(bindings)


def test_validation_error_hides_the_original_payload_and_exception_chain(catalog: dict[str, Any]) -> None:
    outbound = copy.deepcopy(catalog["native_configs"][0]["outbounds"][0])
    secret = "not-a-uuid-sensitive-value"
    outbound["settings"]["vnext"][0]["users"][0]["id"] = secret
    with pytest.raises(MonitorConfigError) as caught:
        validate_native_outbound(outbound)
    assert secret not in str(caught.value)
    assert caught.value.__suppress_context__
