#!/usr/bin/env python3
"""Schedule a panel service restart using the latest on-disk helpers.

Used after in-panel updates so restart logic is not stuck on a stale in-memory module.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--reason", default="panel_restart_script")
    args = parser.parse_args()

    os.chdir(ROOT)
    from app.services.service_control import ensure_restart_helper, restart_panel_service

    ok_h, msg_h = ensure_restart_helper()
    print(msg_h)
    ok, note = restart_panel_service(reason=args.reason, delay_sec=args.delay)
    print(note)
    # Keep process alive briefly so non-daemon restart threads can arm.
    time.sleep(min(2.0, max(0.5, args.delay)))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
