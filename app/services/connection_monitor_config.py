"""Build isolated loopback Xray inputs with explicit routes and a deny default."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.connection_monitor_types import MAX_MONITOR_ENDPOINTS, MonitorConfigError, MonitorEndpoint, MonitorIssue
from app.services.connection_monitor_native import validate_subscription_outbound


@dataclass(frozen=True, slots=True)
class MonitorBinding:
    endpoint: MonitorEndpoint
    port: int


def build_monitor_config(bindings: tuple[MonitorBinding, ...]) -> dict[str, Any]:
    if not bindings or len(bindings) > MAX_MONITOR_ENDPOINTS:
        raise MonitorConfigError(MonitorIssue.CAPACITY)
    ports = [binding.port for binding in bindings]
    keys = [binding.endpoint.endpoint_key for binding in bindings]
    if any(type(port) is not int or not 1024 <= port <= 65535 for port in ports):
        raise MonitorConfigError(MonitorIssue.UNSUPPORTED)
    if len(set(ports)) != len(ports) or len(set(keys)) != len(keys):
        raise MonitorConfigError(MonitorIssue.AMBIGUOUS)
    config: dict[str, Any] = {
        "log": {"loglevel": "none"},
        "inbounds": [],
        "outbounds": [{"tag": "deny", "protocol": "blackhole", "settings": {}}],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }
    for index, binding in enumerate(bindings):
        inbound_tag, outbound_tag = f"probe-in-{index}", f"probe-out-{index}"
        outbound = validate_subscription_outbound(binding.endpoint.outbound())
        outbound["tag"] = outbound_tag
        config["outbounds"].append(outbound)
        config["inbounds"].append({
            "tag": inbound_tag, "listen": "127.0.0.1", "port": binding.port,
            "protocol": "http", "settings": {},
        })
        config["routing"]["rules"].append({
            "type": "field", "inboundTag": [inbound_tag], "outboundTag": outbound_tag,
        })
    return config
