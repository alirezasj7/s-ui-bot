"""Bind native subscription routes to scoped, static PasarGuard host identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.services.connection_monitor_types import (
    MAX_CATALOG_ITEMS,
    MAX_MONITOR_ENDPOINTS,
    MonitorConfigError,
    MonitorEndpoint,
    MonitorHostPlan,
    MonitorIssue,
)
from app.services.connection_monitor_validation import NativeMonitorOutbound, static_hostname, validate_native_outbound
from app.services.pg_object_scope import pg_object_in_staff_scope


_HOST_METADATA = {"admin", "owner", "owner_username", "priority", "status"}
_UNSUPPORTED_HOST_FIELDS = {
    "http_headers", "transport_settings", "mux_settings", "fragment_settings", "noise_settings",
    "random_user_agent", "use_sni_as_host", "vless_route", "ech", "pinned_peer_cert_sha256",
    "verify_peer_cert_by_name", "wireguard_overrides", "subscription_templates", "final_mask_settings", "cipher_suites",
}


class _Host(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", hide_input_in_errors=True)

    id: Annotated[int, Field(ge=1, le=2147483647)]
    remark: Annotated[str, Field(max_length=4096)] = ""
    address: Annotated[list[str], Field(max_length=256)] = Field(default_factory=list)
    inbound_tag: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    port: Annotated[int, Field(ge=1, le=65535)] | None = None
    sni: Annotated[list[str], Field(max_length=16)] = Field(default_factory=list)
    host: Annotated[list[str], Field(max_length=16)] = Field(default_factory=list)
    path: Annotated[str, Field(max_length=2048)] | None = None
    security: str = "inbound_default"
    alpn: Annotated[list[str], Field(max_length=8)] = Field(default_factory=list)
    fingerprint: str = "none"
    allowinsecure: bool | None = None
    is_disabled: bool = False

    @field_validator("address", "sni", "host")
    @classmethod
    def stable_names(cls, value: list[str]) -> list[str]:
        normalized = []
        for name in value:
            try:
                normalized.append(static_hostname(name))
            except ValueError:
                normalized.append(name)
        return sorted(set(normalized))


class _Inbound(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)
    tag: Annotated[str, Field(min_length=1, max_length=256)]
    protocol: str
    network: str


def _has_effect(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_effect(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_effect(item) for item in value)
    return value not in (None, "", False, 0)


def _check_supported_host(host: _Host) -> None:
    extras = host.model_extra or {}
    unknown = extras.keys() - _HOST_METADATA - _UNSUPPORTED_HOST_FIELDS
    configured = any(_has_effect(extras.get(key)) for key in _UNSUPPORTED_HOST_FIELDS)
    # Explicit singleton values make random/default SNI and port selection observable.
    if unknown or configured or len(host.sni) != 1 or host.port is None or not host.inbound_tag or not host.address:
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED)
    if len(host.address) > MAX_MONITOR_ENDPOINTS:
        raise MonitorConfigError(MonitorIssue.CAPACITY)
    try:
        for name in host.address + host.sni + host.host:
            static_hostname(name)
    except ValueError:
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED) from None
    if len(host.host) > 1 or host.allowinsecure is True:
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED)
    if host.security not in {"inbound_default", "tls", "reality"}:
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED)


def _parse_catalog(hosts: object, inbounds: object) -> tuple[list[_Host], dict[str, _Inbound]]:
    try:
        if not isinstance(hosts, list) or not isinstance(inbounds, list):
            raise ValueError("invalid catalog")
        if len(hosts) > MAX_CATALOG_ITEMS or len(inbounds) > MAX_CATALOG_ITEMS:
            raise ValueError("catalog capacity")
        parsed_hosts = [_Host.model_validate(item) for item in hosts]
        parsed_inbounds = [_Inbound.model_validate(item) for item in inbounds]
        by_tag = {item.tag: item for item in parsed_inbounds}
        if len({item.id for item in parsed_hosts}) != len(parsed_hosts) or len(by_tag) != len(parsed_inbounds):
            raise ValueError("duplicate identity")
        return parsed_hosts, by_tag
    except (ValidationError, ValueError):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG) from None


def _matches_host(host: _Host, inbound: _Inbound | None, route: NativeMonitorOutbound) -> bool:
    server, stream = route.settings.vnext[0], route.streamSettings
    if host.is_disabled or inbound is None or inbound.protocol != route.protocol:
        return False
    network = "tcp" if inbound.network == "raw" else inbound.network
    route_network = "tcp" if stream.network == "raw" else stream.network
    if not _could_match_name(host.address, server.address) or network != route_network:
        return False
    if host.port is not None and server.port != host.port:
        return False
    security_settings = stream.realitySettings or stream.tlsSettings
    if host.security != "inbound_default" and host.security != stream.security:
        return False
    if host.sni and not _could_match_name(host.sni, security_settings.serverName):
        return False
    if not _matches_security(host, security_settings.model_dump()):
        return False
    if stream.wsSettings:
        return _matches_ws(host, stream.wsSettings.model_dump())
    return True


def _could_match_name(names: list[str], value: str) -> bool:
    if not names:
        return True
    for name in names:
        try:
            if static_hostname(name) == value:
                return True
        except ValueError:
            # A dynamic host might have produced this native route; never pick
            # the static contender merely because its competitor is unsupported.
            return True
    return False


def _matches_security(host: _Host, settings: dict[str, Any]) -> bool:
    if host.fingerprint != "none" and host.fingerprint != settings.get("fingerprint"):
        return False
    return not host.alpn or host.alpn == settings.get("alpn")


def _matches_ws(host: _Host, settings: dict[str, Any]) -> bool:
    if host.path is not None and host.path != settings["path"]:
        return False
    headers = settings["headers"]
    header_hosts = [value for key, value in headers.items() if key.lower() == "host"]
    effective_hosts = set(header_hosts + ([settings["host"]] if settings["host"] else []))
    if len(effective_hosts) > 1:
        return False
    return not host.host or effective_hosts == set(host.host)


def _native_routes(configs: object) -> tuple[list[NativeMonitorOutbound], set[str]]:
    if not isinstance(configs, list) or len(configs) > MAX_CATALOG_ITEMS:
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    routes = []
    unsupported_addresses: set[str] = set()
    for config in configs:
        if not isinstance(config, dict) or not isinstance(config.get("outbounds"), list):
            raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
        # The native generator prepends its main route. Template routes are never executed.
        outbounds = config["outbounds"]
        if not outbounds or len(outbounds) > 16:
            raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
        main = outbounds[0]
        if not isinstance(main, dict):
            raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
        if main.get("protocol") != "vless":
            continue
        try:
            routes.append(validate_native_outbound(main))
        except MonitorConfigError:
            try:
                address = static_hostname(main["settings"]["vnext"][0]["address"])
            except (KeyError, IndexError, TypeError, ValueError):
                raise MonitorConfigError(MonitorIssue.INVALID_CATALOG) from None
            unsupported_addresses.add(address)
    return routes, unsupported_addresses


def _route_for_host(host: _Host, hosts: list[_Host], inbounds: dict[str, _Inbound],
                    routes: list[NativeMonitorOutbound]) -> dict[str, Any]:
    candidates: dict[str, dict[str, Any]] = {}
    for route in routes:
        if not _matches_host(host, inbounds.get(host.inbound_tag), route):
            continue
        matches = [item.id for item in hosts if _matches_host(item, inbounds.get(item.inbound_tag), route)]
        if matches != [host.id]:
            raise MonitorConfigError(MonitorIssue.AMBIGUOUS)
        config = route.config()
        config["settings"]["vnext"][0]["address"] = host.address[0]
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        candidates[serialized] = config
    if not candidates:
        raise MonitorConfigError(MonitorIssue.MISSING_ROUTE)
    if len(candidates) != 1:
        raise MonitorConfigError(MonitorIssue.AMBIGUOUS)
    return next(iter(candidates.values()))


def _expand_host(host: _Host, config: dict[str, Any], *, account_revision: str) -> tuple[MonitorEndpoint, ...]:
    endpoints = []
    for address in host.address:
        config["settings"]["vnext"][0]["address"] = address
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(f"{host.id}:{address}".encode()).hexdigest()
        generation = hashlib.sha256(f"native-v1:{account_revision}:{host.inbound_tag}:{serialized}".encode()).hexdigest()
        endpoints.append(MonitorEndpoint(host.id, key, generation, serialized))
    return tuple(endpoints)


def _plan_host(host: _Host, hosts: list[_Host], inbounds: dict[str, _Inbound],
               routes: list[NativeMonitorOutbound], *, account_revision: str) -> MonitorHostPlan:
    _check_supported_host(host)
    config = _route_for_host(host, hosts, inbounds, routes)
    for address in host.address:
        config["settings"]["vnext"][0]["address"] = address
        route = validate_native_outbound(config)
        matches = [item.id for item in hosts if _matches_host(item, inbounds.get(item.inbound_tag), route)]
        if matches != [host.id]:
            raise MonitorConfigError(MonitorIssue.AMBIGUOUS)
    return MonitorHostPlan(host.id, _expand_host(host, config, account_revision=account_revision))


def plan_monitor_hosts(*, hosts: object, inbounds: object, native_configs: object,
                       selected_ids: tuple[int, ...], staff: Mapping[str, Any],
                       account_revision: str) -> tuple[MonitorHostPlan, ...]:
    """Plan a bounded selection from one authenticated principal's full catalog.

    Account ownership/activity and the explicit Owner capability belong to the use
    case calling this pure mapper. No network, DB mutation or authorization grant
    occurs here. Missing ownership metadata fails closed.
    """
    if not isinstance(account_revision, str) or not account_revision or len(account_revision) > 128:
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    if not isinstance(selected_ids, tuple):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    if len(selected_ids) > MAX_MONITOR_ENDPOINTS or len(set(selected_ids)) != len(selected_ids):
        raise MonitorConfigError(MonitorIssue.CAPACITY)
    if any(type(item) is not int or not 1 <= item <= 2147483647 for item in selected_ids):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    parsed_hosts, by_tag = _parse_catalog(hosts, inbounds)
    routes, unsupported_addresses = _native_routes(native_configs)
    raw_by_id = {item["id"]: item for item in hosts}
    by_id = {item.id: item for item in parsed_hosts}
    scope_staff = {**staff, "pg_is_owner": staff.get("pg_is_owner") is True}
    plans = []
    for host_id in selected_ids:
        host = by_id.get(host_id)
        try:
            if host is None or host.is_disabled:
                raise MonitorConfigError(MonitorIssue.HOST_UNAVAILABLE)
            if not pg_object_in_staff_scope(raw_by_id[host_id], scope_staff):
                raise MonitorConfigError(MonitorIssue.OUT_OF_SCOPE)
            if set(host.address) & unsupported_addresses:
                raise MonitorConfigError(MonitorIssue.UNSUPPORTED)
            plans.append(_plan_host(host, parsed_hosts, by_tag, routes, account_revision=account_revision))
        except MonitorConfigError as exc:
            plans.append(MonitorHostPlan(host_id, issue=exc.issue))
    if sum(len(plan.endpoints) for plan in plans) > MAX_MONITOR_ENDPOINTS:
        return tuple(MonitorHostPlan(plan.host_id, issue=MonitorIssue.CAPACITY) if plan.is_ready else plan for plan in plans)
    return tuple(plans)
