"""What the PasarGuard overview (/pg) shows, built from figures already fetched.

The owner sees the panel's system-wide counts; a reseller or panel staff sees only the counts of
users they own (``build_reseller_pg_overview``). Both become the same shape here, so the page
draws one set of cards. Pure functions: no I/O, no PasarGuard calls.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# PasarGuard has named these counters differently across versions.
_TOTAL_KEYS = ("total_user", "total_users", "users_total")
_ONLINE_KEYS = ("online_users", "users_online")
_ACTIVE_KEYS = ("active_users", "users_active")
_EXPIRED_KEYS = ("expired_users", "users_expired")
_LIMITED_KEYS = ("limited_users", "users_limited")
_DISABLED_KEYS = ("disabled_users", "users_disabled")
_ON_HOLD_KEYS = ("on_hold_users", "users_on_hold")
_VERSION_KEYS = ("version", "panel_version")


@dataclass(frozen=True, slots=True)
class UserCounts:
    total: int
    online: int
    active: int
    expired: int
    limited: int
    disabled: int
    on_hold: int


@dataclass(frozen=True, slots=True)
class Segment:
    key: str
    label: str
    count: int
    pct: float


# Order and labels of the share bar; online users are a subset of active ones, so not a segment.
SEGMENTS = (
    ("active", "فعال"),
    ("expired", "منقضی"),
    ("limited", "اتمام حجم"),
    ("on_hold", "در انتظار"),
    ("disabled", "غیرفعال"),
)


def _count(raw: Mapping[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return 0


def owner_user_counts(system_stats: Mapping[str, Any] | None) -> UserCounts:
    raw = system_stats or {}
    return UserCounts(
        total=_count(raw, _TOTAL_KEYS),
        online=_count(raw, _ONLINE_KEYS),
        active=_count(raw, _ACTIVE_KEYS),
        expired=_count(raw, _EXPIRED_KEYS),
        limited=_count(raw, _LIMITED_KEYS),
        disabled=_count(raw, _DISABLED_KEYS),
        on_hold=_count(raw, _ON_HOLD_KEYS),
    )


def owned_user_counts(user_stats: Mapping[str, Any] | None) -> UserCounts:
    """Counts of a reseller's or staff member's own users (``_owned_user_stats``)."""
    raw = user_stats or {}
    return UserCounts(**{field: _count(raw, (field,)) for field in UserCounts.__slots__})


def segments(counts: UserCounts) -> list[Segment]:
    """The share bar: each status as a share of the users counted in it; empty when none."""
    values = [(key, label, int(getattr(counts, key))) for key, label in SEGMENTS]
    whole = sum(value for _key, _label, value in values)
    if whole <= 0:
        return []
    return [Segment(key=k, label=lbl, count=v, pct=round(v * 100 / whole, 1)) for k, lbl, v in values if v > 0]


def panel_version(system_stats: Mapping[str, Any] | None) -> str | None:
    raw = system_stats or {}
    for key in _VERSION_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:32]
    return None


def node_counts(nodes: list[Mapping[str, Any]] | None) -> tuple[int, int]:
    """(connected, total) from overview node cards."""
    cards = [n for n in nodes or [] if isinstance(n, Mapping)]
    return sum(1 for n in cards if n.get("status_kind") == "ok"), len(cards)


def nodes_state(connected: int, total: int) -> str:
    if total == 0:
        return "neutral"
    if connected == total:
        return "ok"
    return "err" if connected == 0 else "warn"


def overview_view(
    *,
    owner: bool,
    system_stats: Mapping[str, Any] | None,
    user_stats: Mapping[str, Any] | None,
    nodes: list[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Everything the cards need. A non-owner never gets panel-wide counts, version or nodes."""
    counts = owner_user_counts(system_stats) if owner else owned_user_counts(user_stats)
    connected, total = node_counts(nodes) if owner else (0, 0)
    return {
        "counts": counts,
        "segments": segments(counts),
        "version": panel_version(system_stats) if owner else None,
        "nodes_connected": connected,
        "nodes_total": total,
        "nodes_state": nodes_state(connected, total),
    }
