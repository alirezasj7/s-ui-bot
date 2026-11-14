#!/usr/bin/env python3
"""Apply Alembic migrations for the configured (or provided) DATABASE_URL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="", help="Override DATABASE_URL")
    p.add_argument("--downgrade", action="store_true", help="Downgrade one revision")
    p.add_argument("--stamp-head", action="store_true", help="Stamp head without running DDL")
    p.add_argument("--current", action="store_true", help="Print current revision")
    args = p.parse_args()

    from app.config import get_settings
    from app.db import alembic_runner

    url = args.url or get_settings().database_url
    if args.current:
        print(alembic_runner.current_revision(url) or "(none)")
        return 0
    if args.stamp_head:
        alembic_runner.stamp_head(url)
        print("stamped head")
        return 0
    if args.downgrade:
        alembic_runner.downgrade_one(url)
        print("downgraded -1")
        return 0
    alembic_runner.upgrade_head(url)
    print("upgraded to", alembic_runner.current_revision(url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
