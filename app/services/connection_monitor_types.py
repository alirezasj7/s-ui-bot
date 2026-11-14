"""Immutable subscription route plans and safe connection-test failures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.py_compat import StrEnum

MAX_MONITOR_ENDPOINTS = 12
MAX_CATALOG_ITEMS = 1000


class MonitorIssue(StrEnum):
    INVALID_CATALOG = "invalid_catalog"
    HOST_UNAVAILABLE = "host_unavailable"
    CONFIG_UNAVAILABLE = "config_unavailable"
    OUT_OF_SCOPE = "out_of_scope"
    UNSUPPORTED = "unsupported_route"
    AMBIGUOUS = "ambiguous_route"
    MISSING_ROUTE = "missing_route"
    CAPACITY = "endpoint_capacity"


class MonitorConfigError(ValueError):
    """Expose a fixed diagnostic code rather than panel payloads or secrets."""

    def __init__(self, issue: MonitorIssue) -> None:
        super().__init__(issue.value)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class MonitorEndpoint:
    host_id: int | None
    endpoint_key: str
    generation: str
    outbound_json: str = field(repr=False)
    config_key: str | None = None

    def outbound(self) -> dict[str, Any]:
        return json.loads(self.outbound_json)


@dataclass(frozen=True, slots=True)
class MonitorConfigPlan:
    config_key: str
    endpoints: tuple[MonitorEndpoint, ...] = ()
    issue: MonitorIssue | None = None

    @property
    def is_ready(self) -> bool:
        return self.issue is None and bool(self.endpoints)


@dataclass(frozen=True, slots=True)
class MonitorHostPlan:
    """Retain the pure host-planning API while runtime selections use subscriptions."""

    host_id: int
    endpoints: tuple[MonitorEndpoint, ...] = ()
    issue: MonitorIssue | None = None

    @property
    def is_ready(self) -> bool:
        return self.issue is None and bool(self.endpoints)
