"""Select exact native subscription outbounds without consulting panel hosts."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field

from app.services.connection_monitor_types import (
    MAX_CATALOG_ITEMS, MAX_MONITOR_ENDPOINTS, MonitorConfigError, MonitorConfigPlan,
    MonitorEndpoint, MonitorIssue,
)
from app.services.connection_monitor_native import NativeProtocolDetails, protocol_details, validate_subscription_outbound


CONFIG_KEY_PATTERN = r"[A-Za-z0-9_-]{43}"


@dataclass(frozen=True, slots=True)
class MonitorConfigEntry:
    config_key: str
    name: str
    position: int
    outbound_json: str = field(repr=False)
    details: NativeProtocolDetails
    issue: MonitorIssue | None = None


def validate_config_key(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(CONFIG_KEY_PATTERN, value) is None:
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    return value


def _entry(config: object, position: int, occurrences: Counter[str]) -> MonitorConfigEntry:
    if not isinstance(config, dict):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    outbounds = config.get("outbounds")
    name = config.get("remarks", "")
    if (not isinstance(outbounds, list) or not 1 <= len(outbounds) <= 16
            or not isinstance(outbounds[0], dict) or not isinstance(name, str) or len(name) > 4096):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    try:
        serialized = json.dumps(outbounds[0], sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG) from None
    identity = json.dumps([name, serialized], ensure_ascii=True, separators=(",", ":"))
    occurrence = occurrences[identity]
    occurrences[identity] += 1
    digest = hashlib.sha256(f"subscription-v1:{identity}:{occurrence}".encode()).digest()
    key = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    issue = None
    try:
        validate_subscription_outbound(outbounds[0])
    except MonitorConfigError as exc:
        issue = exc.issue
    label = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127).strip()
    return MonitorConfigEntry(key, label[:128] or f"کانفیگ {position + 1}", position, serialized, protocol_details(outbounds[0]), issue)


def subscription_entries(native_configs: object) -> tuple[MonitorConfigEntry, ...]:
    """Keep native array order, duplicate labels and identical-entry occurrences."""
    if not isinstance(native_configs, list) or len(native_configs) > MAX_CATALOG_ITEMS:
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    occurrences: Counter[str] = Counter()
    return tuple(_entry(config, position, occurrences) for position, config in enumerate(native_configs))


def _plan(entry: MonitorConfigEntry, account_revision: str) -> MonitorConfigPlan:
    if entry.issue is not None:
        return MonitorConfigPlan(entry.config_key, issue=entry.issue)
    key = hashlib.sha256(f"subscription:{entry.config_key}".encode()).hexdigest()
    generation = hashlib.sha256(f"native-v2:{account_revision}:{entry.outbound_json}".encode()).hexdigest()
    endpoint = MonitorEndpoint(None, key, generation, entry.outbound_json, config_key=entry.config_key)
    return MonitorConfigPlan(entry.config_key, (endpoint,))


def plan_monitor_configs(*, native_configs: object, selected_keys: tuple[str, ...],
                         account_revision: str) -> tuple[MonitorConfigPlan, ...]:
    """Bind selections by content identity; a reorder can never select another route."""
    if not isinstance(account_revision, str) or not account_revision or len(account_revision) > 128:
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    if not isinstance(selected_keys, tuple):
        raise MonitorConfigError(MonitorIssue.INVALID_CATALOG)
    for key in selected_keys:
        validate_config_key(key)
    if len(selected_keys) > MAX_MONITOR_ENDPOINTS or len(set(selected_keys)) != len(selected_keys):
        raise MonitorConfigError(MonitorIssue.CAPACITY)
    entries = {entry.config_key: entry for entry in subscription_entries(native_configs)}
    return tuple(_plan(entries[key], account_revision) if key in entries else
                 MonitorConfigPlan(key, issue=MonitorIssue.CONFIG_UNAVAILABLE) for key in selected_keys)
