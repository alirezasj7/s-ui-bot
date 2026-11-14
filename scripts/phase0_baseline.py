#!/usr/bin/env python3
"""Phase 0 baseline: backup DB + configs, record git/version, verify restore.

Usage:
  .venv/bin/python -m scripts.phase0_baseline
  .venv/bin/python -m scripts.phase0_baseline --note "pre-phase-a"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="PGClock Phase 0 production baseline")
    parser.add_argument("--note", default="phase0-pre-migration")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    from app.services.baseline import create_phase0_baseline

    result = create_phase0_baseline(
        note=args.note,
        verify_restore=not args.skip_verify,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
