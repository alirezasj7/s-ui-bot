"""Panel request timing — observation only.

Does not change auth, ACL, tenant resolution, or response bodies.
Handlers may call ``mark`` after Depends() so ``handler`` approximates
post-auth time without modifying ``require_staff``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("pgclock.panel_timing")

# Paths where we always record timing (exact or prefix).
_EXACT = frozenset(
    {
        "/home",
        "/home/body",
        "/pg",
        "/pg/body",
        "/pg/users",
        "/plans",
        "/tickets",
        "/finance",
        "/dashboard",
        "/inbox",
    }
)
_PREFIXES = ("/pg/",)


def should_time(path: str) -> bool:
    p = path or ""
    if p in _EXACT:
        return True
    return any(p.startswith(pref) for pref in _PREFIXES)


def begin(request: Any) -> None:
    request.state.panel_timing = {
        "t0": time.perf_counter(),
        "marks": {},
    }


def mark(request: Any, name: str) -> None:
    """Record a named timestamp relative to request start."""
    state = getattr(request.state, "panel_timing", None)
    if not isinstance(state, dict):
        return
    marks = state.setdefault("marks", {})
    if name not in marks:
        marks[name] = time.perf_counter()


def snapshot(request: Any) -> dict[str, Any] | None:
    state = getattr(request.state, "panel_timing", None)
    if not isinstance(state, dict) or "t0" not in state:
        return None
    t0 = float(state["t0"])
    now = time.perf_counter()
    total_ms = round((now - t0) * 1000.0, 1)
    marks = state.get("marks") or {}
    out: dict[str, Any] = {"total_ms": total_ms, "path": request.url.path}
    # handler ≈ first line of route after Depends (auth/tenant/ACL done)
    if "handler" in marks:
        out["auth_ms"] = round((float(marks["handler"]) - t0) * 1000.0, 1)
        out["page_ms"] = round((now - float(marks["handler"])) * 1000.0, 1)
    if "page_data" in marks and "handler" in marks:
        out["page_data_ms"] = round(
            (float(marks["page_data"]) - float(marks["handler"])) * 1000.0, 1
        )
    return out


def finish_log(request: Any, *, status_code: int) -> dict[str, Any] | None:
    snap = snapshot(request)
    if not snap:
        return None
    snap["status"] = int(status_code)
    total = float(snap.get("total_ms") or 0)
    # Slow paths at INFO; fast at DEBUG — no behavior change either way.
    if total >= 200:
        logger.info(
            "panel_timing path=%s status=%s total_ms=%s auth_ms=%s page_ms=%s page_data_ms=%s",
            snap.get("path"),
            snap.get("status"),
            snap.get("total_ms"),
            snap.get("auth_ms"),
            snap.get("page_ms"),
            snap.get("page_data_ms"),
        )
    else:
        logger.debug(
            "panel_timing path=%s status=%s total_ms=%s auth_ms=%s page_ms=%s",
            snap.get("path"),
            snap.get("status"),
            snap.get("total_ms"),
            snap.get("auth_ms"),
            snap.get("page_ms"),
        )
    return snap


def server_timing_header(snap: dict[str, Any] | None) -> str | None:
    """Optional Server-Timing value for browser DevTools (private panel only)."""
    if not snap:
        return None
    parts: list[str] = []
    total = snap.get("total_ms")
    if total is not None:
        parts.append(f"total;dur={total}")
    auth = snap.get("auth_ms")
    if auth is not None:
        parts.append(f"auth;dur={auth}")
    page = snap.get("page_ms")
    if page is not None:
        parts.append(f"page;dur={page}")
    pdata = snap.get("page_data_ms")
    if pdata is not None:
        parts.append(f"page_data;dur={pdata}")
    return ", ".join(parts) if parts else None
