"""Local host CPU / RAM metrics (Linux /proc; no extra deps)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

_CPU_SAMPLE: tuple[float, float, float] | None = None  # idle, total, monotonic
_CPU_LOCK = threading.Lock()
_MEMINFO = Path("/proc/meminfo")
_STAT = Path("/proc/stat")


def _read_cpu_times() -> tuple[float, float] | None:
    try:
        line = _STAT.read_text(encoding="utf-8").splitlines()[0]
    except OSError:
        return None
    parts = line.split()
    if not parts or parts[0] != "cpu" or len(parts) < 5:
        return None
    try:
        nums = [float(x) for x in parts[1:]]
    except ValueError:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)  # idle + iowait
    total = sum(nums)
    return idle, total


def cpu_percent(*, wait_sec: float = 0.12) -> float | None:
    """Return CPU usage percent using /proc/stat delta sampling."""
    global _CPU_SAMPLE
    with _CPU_LOCK:
        now = time.monotonic()
        cur = _read_cpu_times()
        if cur is None:
            return None
        idle, total = cur
        prev = _CPU_SAMPLE
        _CPU_SAMPLE = (idle, total, now)
        if prev is None or (now - prev[2]) < 0.05:
            if wait_sec > 0:
                time.sleep(wait_sec)
                cur2 = _read_cpu_times()
                if cur2 is None:
                    return None
                idle2, total2 = cur2
                _CPU_SAMPLE = (idle2, total2, time.monotonic())
                d_total = total2 - total
                d_idle = idle2 - idle
            else:
                return None
        else:
            d_total = total - prev[1]
            d_idle = idle - prev[0]
    if d_total <= 0:
        return 0.0
    used = max(0.0, min(100.0, (1.0 - (d_idle / d_total)) * 100.0))
    return round(used, 1)


def memory_stats() -> dict[str, Any] | None:
    """Return RAM totals from /proc/meminfo (bytes + percent)."""
    try:
        text = _MEMINFO.read_text(encoding="utf-8")
    except OSError:
        return None
    vals: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        bits = rest.strip().split()
        if not bits:
            continue
        try:
            kb = int(bits[0])
        except ValueError:
            continue
        vals[key] = kb * 1024
    total = vals.get("MemTotal")
    available = vals.get("MemAvailable")
    if not total or total <= 0:
        return None
    if available is None:
        free = vals.get("MemFree", 0)
        cached = vals.get("Cached", 0) + vals.get("Buffers", 0)
        available = free + cached
    used = max(0, total - available)
    pct = round(min(100.0, (used / total) * 100.0), 1)
    return {
        "total": total,
        "used": used,
        "available": available,
        "percent": pct,
    }


def format_bytes_short(n: int | float | None) -> str:
    """Host metrics short size — Persian labels (گیگ/مگ), same IEC base as format_bytes."""
    from app.services.formatting import format_bytes

    return format_bytes(n, precision=1)


def format_memory_ratio(used: int | float | None, total: int | float | None) -> str:
    from app.services.formatting import format_bytes_ratio

    return format_bytes_ratio(used, total, precision=1)


def cpu_core_count() -> int | None:
    """Logical CPU count from /proc/stat (cpu0..cpuN) or os.cpu_count()."""
    try:
        lines = _STAT.read_text(encoding="utf-8").splitlines()
        cores = sum(1 for ln in lines if ln.startswith("cpu") and ln[3:4].isdigit())
        if cores > 0:
            return cores
    except OSError:
        pass
    try:
        import os

        n = os.cpu_count()
        return int(n) if n else None
    except Exception:
        return None


def host_metrics(*, wait_cpu: float = 0.12) -> dict[str, Any]:
    """Snapshot used by the overall home dashboard."""
    cpu = cpu_percent(wait_sec=wait_cpu)
    mem = memory_stats()
    cores = cpu_core_count()
    return {
        "cpu_percent": cpu,
        "cpu_cores": cores,
        "memory": mem,
        "memory_used_text": format_bytes_short(mem["used"]) if mem else "—",
        "memory_total_text": format_bytes_short(mem["total"]) if mem else "—",
        "memory_ratio_text": (
            format_memory_ratio(mem["used"], mem["total"]) if mem else "—"
        ),
        "memory_percent": mem["percent"] if mem else None,
        "ok": cpu is not None or mem is not None,
    }
