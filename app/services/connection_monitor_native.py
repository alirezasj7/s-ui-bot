"""Validate bounded native proxy outbounds without rewriting their Xray fields."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.connection_monitor_types import MonitorConfigError, MonitorIssue
from app.services.connection_monitor_validation import static_hostname


PROXY_PROTOCOLS = frozenset({"vless", "vmess", "trojan", "shadowsocks"})
TRANSPORTS = frozenset({"tcp", "raw", "ws", "grpc", "gun", "xhttp", "splithttp", "http", "h2", "httpupgrade", "kcp", "quic"})
FORBIDDEN_FIELDS = frozenset({
    "proxySettings", "sendThrough", "dialerProxy", "certificates", "certificateFile", "keyFile", "masterKeyLog",
})
MAX_OUTBOUND_BYTES = 256 * 1024
MAX_NATIVE_DEPTH = 20


@dataclass(frozen=True, slots=True)
class NativeProtocolDetails:
    protocol: str
    transport: str
    security: str
    port: int | None


def protocol_details(payload: dict[str, Any]) -> NativeProtocolDetails:
    protocol = payload.get("protocol")
    protocol = protocol if isinstance(protocol, str) and protocol in PROXY_PROTOCOLS else "unknown"
    stream = payload.get("streamSettings")
    stream = stream if isinstance(stream, dict) else {}
    network = stream.get("network", "tcp")
    network = network if isinstance(network, str) and network in TRANSPORTS else "unknown"
    transport = {"raw": "tcp", "splithttp": "xhttp", "gun": "grpc", "h2": "http"}.get(network, network)
    security = stream.get("security", "none")
    security = security if isinstance(security, str) and security in {"tls", "reality"} else ""
    settings = payload.get("settings")
    settings = settings if isinstance(settings, dict) else {}
    servers = settings.get("vnext" if protocol in {"vless", "vmess"} else "servers", [])
    server = servers[0] if isinstance(servers, list) and servers and isinstance(servers[0], dict) else {}
    port = server.get("port")
    return NativeProtocolDetails(protocol, transport, security, port if type(port) is int and 1 <= port <= 65535 else None)


def _unsupported() -> MonitorConfigError:
    return MonitorConfigError(MonitorIssue.UNSUPPORTED)


def _bounded_json(value: object, *, depth: int = 0) -> None:
    if depth > MAX_NATIVE_DEPTH:
        raise _unsupported()
    if isinstance(value, dict):
        if len(value) > 256 or any(not isinstance(key, str) or key in FORBIDDEN_FIELDS for key in value):
            raise _unsupported()
        if "allowInsecure" in value and value["allowInsecure"] is not False:
            raise _unsupported()
        for item in value.values():
            _bounded_json(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 256:
            raise _unsupported()
        for item in value:
            _bounded_json(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 16384:
            raise _unsupported()
    elif value is not None and type(value) not in (bool, int, float):
        raise _unsupported()


def _single_item(value: object) -> dict[str, Any]:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise _unsupported()
    return value[0]


def _secret(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise _unsupported()
    return value


def _validate_server(settings: dict[str, Any], protocol: str) -> None:
    server = _single_item(settings.get("vnext" if protocol in {"vless", "vmess"} else "servers"))
    address, port = server.get("address"), server.get("port")
    if not isinstance(address, str) or type(port) is not int or not 1 <= port <= 65535:
        raise _unsupported()
    try:
        static_hostname(address)
    except ValueError:
        raise _unsupported() from None
    if protocol in {"vless", "vmess"}:
        user = _single_item(server.get("users"))
        try:
            UUID(_secret(user.get("id")))
        except ValueError:
            raise _unsupported() from None
    else:
        _secret(server.get("password"))
        if protocol == "shadowsocks":
            _secret(server.get("method"))


def _validate_security(stream: dict[str, Any]) -> None:
    security = stream.get("security", "none")
    if not isinstance(security, str) or security not in {"none", "", "tls", "reality"}:
        raise _unsupported()
    for name in ("tls", "reality"):
        settings = stream.get(name + "Settings")
        if settings is None:
            if security == name:
                raise _unsupported()
            continue
        if not isinstance(settings, dict) or security != name:
            raise _unsupported()
        if "allowInsecure" in settings and settings["allowInsecure"] is not False:
            raise _unsupported()
        if settings.get("show", False) is not False:
            raise _unsupported()
        server_name = settings.get("serverName")
        if server_name is not None:
            if not isinstance(server_name, str):
                raise _unsupported()
            try:
                if server_name:
                    static_hostname(server_name)
            except ValueError:
                raise _unsupported() from None


def validate_subscription_outbound(payload: object) -> dict[str, Any]:
    """Preserve native fields; the pinned core validates its own schema at startup."""
    if not isinstance(payload, dict) or set(payload) - {"protocol", "tag", "settings", "streamSettings", "mux"}:
        raise _unsupported()
    protocol, settings = payload.get("protocol"), payload.get("settings")
    if not isinstance(protocol, str) or protocol not in PROXY_PROTOCOLS or not isinstance(settings, dict):
        raise _unsupported()
    if not isinstance(payload.get("tag"), str) or not 1 <= len(payload["tag"]) <= 128:
        raise _unsupported()
    _bounded_json(payload)
    try:
        if len(json.dumps(payload, allow_nan=False).encode()) > MAX_OUTBOUND_BYTES:
            raise _unsupported()
    except (TypeError, ValueError, RecursionError):
        raise _unsupported() from None
    _validate_server(settings, protocol)
    stream = payload.get("streamSettings", {})
    if not isinstance(stream, dict):
        raise _unsupported()
    network = stream.get("network", "tcp")
    if not isinstance(network, str) or network not in TRANSPORTS:
        raise _unsupported()
    _validate_security(stream)
    return copy.deepcopy(payload)
