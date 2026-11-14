"""Normalize local / PasarGuard host CPU+RAM into dashboard gauge payloads."""

from __future__ import annotations

from typing import Any

from app.services.host_metrics import (
    format_bytes_short,
    format_memory_ratio,
    host_metrics,
)


def tone_class(pct: float | None) -> str:
    if pct is None:
        return "neutral"
    if pct >= 90:
        return "err"
    if pct >= 75:
        return "warn"
    return "ok"


def empty_host_gauges() -> dict[str, Any]:
    return {
        "ok": False,
        "cpu_percent": None,
        "cpu_cores": None,
        "memory_percent": None,
        "memory_used": None,
        "memory_total": None,
        "memory_used_text": "—",
        "memory_total_text": "—",
        "memory_ratio_text": "—",
        "cpu_tone": "neutral",
        "mem_tone": "neutral",
    }


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    f = _as_float(value)
    if f is None:
        return None
    try:
        return int(f)
    except (TypeError, ValueError):
        return None


def _clamp_pct(value: float | None) -> float | None:
    if value is None:
        return None
    # PasarGuard and /proc both report 0..100 (not 0..1 fractions).
    return round(max(0.0, min(100.0, float(value))), 1)


def build_host_gauges(
    *,
    cpu_percent: float | None = None,
    cpu_cores: int | None = None,
    memory_used: int | None = None,
    memory_total: int | None = None,
    memory_percent: float | None = None,
) -> dict[str, Any]:
    """Build the same gauge dict used by home/dashboard/pg overview rings."""
    out = empty_host_gauges()
    cpu = _clamp_pct(cpu_percent if isinstance(cpu_percent, (int, float)) else None)
    mem_pct = memory_percent
    if mem_pct is None and memory_used is not None and memory_total:
        try:
            mem_pct = (float(memory_used) / float(memory_total)) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            mem_pct = None
    mem_pct = _clamp_pct(mem_pct if isinstance(mem_pct, (int, float)) else None)

    used = int(memory_used) if isinstance(memory_used, (int, float)) and memory_used >= 0 else None
    total = int(memory_total) if isinstance(memory_total, (int, float)) and memory_total > 0 else None

    out.update(
        {
            "ok": cpu is not None or mem_pct is not None,
            "cpu_percent": cpu,
            "cpu_cores": cpu_cores if isinstance(cpu_cores, int) and cpu_cores > 0 else None,
            "memory_percent": mem_pct,
            "memory_used": used,
            "memory_total": total,
            "memory_used_text": format_bytes_short(used) if used is not None else "—",
            "memory_total_text": format_bytes_short(total) if total is not None else "—",
            "memory_ratio_text": (
                format_memory_ratio(used, total) if used is not None and total else "—"
            ),
            "cpu_tone": tone_class(cpu),
            "mem_tone": tone_class(mem_pct),
        }
    )
    return out


def local_host_gauges(*, wait_cpu: float = 0.12) -> dict[str, Any]:
    snap = host_metrics(wait_cpu=wait_cpu)
    return build_host_gauges(
        cpu_percent=snap.get("cpu_percent"),
        cpu_cores=snap.get("cpu_cores"),
        memory_used=(snap.get("memory") or {}).get("used") if isinstance(snap.get("memory"), dict) else None,
        memory_total=(snap.get("memory") or {}).get("total") if isinstance(snap.get("memory"), dict) else None,
        memory_percent=snap.get("memory_percent"),
    )


def gauges_from_pg_system_stats(stats: dict | None) -> dict[str, Any]:
    """Map PasarGuard ``GET /api/system`` fields onto local-style gauges.

    Only CPU/RAM are surfaced — never expose unrelated host keys to the panel.
    """
    if not isinstance(stats, dict):
        return empty_host_gauges()

    cpu = None
    for key in ("cpu_usage", "cpu", "cpu_percent"):
        if key in stats:
            cpu = _as_float(stats.get(key))
            break

    cores = None
    for key in ("cpu_cores", "cores", "cpu_count"):
        if key in stats:
            cores = _as_int(stats.get(key))
            break

    mem_used = None
    mem_total = None
    for uk, tk in (
        ("mem_used", "mem_total"),
        ("memory_used", "memory_total"),
        ("ram_used", "ram_total"),
    ):
        if uk in stats or tk in stats:
            mem_used = _as_int(stats.get(uk))
            mem_total = _as_int(stats.get(tk))
            break

    mem_pct = None
    for key in ("memory_percent", "mem_percent", "ram_percent"):
        if key in stats:
            mem_pct = _as_float(stats.get(key))
            break

    return build_host_gauges(
        cpu_percent=cpu,
        cpu_cores=cores,
        memory_used=mem_used,
        memory_total=mem_total,
        memory_percent=mem_pct,
    )


def gauges_json(host: dict[str, Any]) -> dict[str, Any]:
    """Lean JSON for gauge polling endpoints."""
    return {
        "cpu_percent": host.get("cpu_percent"),
        "memory_percent": host.get("memory_percent"),
        "memory_used_text": host.get("memory_used_text"),
        "memory_total_text": host.get("memory_total_text"),
        "memory_ratio_text": host.get("memory_ratio_text"),
        "cpu_cores": host.get("cpu_cores"),
        "cpu_tone": host.get("cpu_tone") or tone_class(
            host.get("cpu_percent") if isinstance(host.get("cpu_percent"), (int, float)) else None
        ),
        "mem_tone": host.get("mem_tone") or tone_class(
            host.get("memory_percent")
            if isinstance(host.get("memory_percent"), (int, float))
            else None
        ),
    }
