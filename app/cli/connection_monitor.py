"""Validate pinned Xray startup with synthetic PGClockBot routes and no relay traffic."""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.connection_monitor_subscription import plan_monitor_configs, subscription_entries
from app.services.connection_monitor_types import MonitorEndpoint
from app.services.xray_probe import run_xray_batch
from app.services.xray_probe_resources import XrayBinary


@dataclass(frozen=True, slots=True)
class CoreValidation:
    endpoints: int
    startup_seconds: float
    cleanup_seconds: float
    child_reaped: bool
    peak_child_rss_kib: int


async def validate_core(binary: XrayBinary, endpoints: tuple[MonitorEndpoint, ...]) -> CoreValidation:
    started = time.monotonic()
    async with run_xray_batch(binary, endpoints) as batch:
        if not batch.is_alive or len(batch.bindings) != len(endpoints):
            raise ValueError("Synthetic core readiness failed")
        ready = time.monotonic()
        process = batch.process
    stopped = time.monotonic()
    if process.returncode is None:
        raise ValueError("Synthetic core cleanup failed")
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return CoreValidation(len(endpoints), round(ready - started, 4), round(stopped - ready, 4), True,
                          int(rss / 1024) if sys.platform == "darwin" else int(rss))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/connection_monitor_native.json"
        catalog = json.loads(fixture.read_text(encoding="utf-8"))
        entries = subscription_entries(catalog["native_configs"])
        plans = plan_monitor_configs(**catalog, selected_keys=tuple(entry.config_key for entry in entries), account_revision="synthetic")
        if not all(plan.is_ready for plan in plans):
            raise ValueError("Synthetic route mapping failed")
        endpoints = tuple(endpoint for plan in plans for endpoint in plan.endpoints)
        result = asyncio.run(validate_core(XrayBinary(args.binary, args.sha256), endpoints))
    except (ValueError, OSError, TimeoutError):
        print("PGClockBot synthetic core validation failed.", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
