#!/usr/bin/env python3
"""Migrate SQLite PGClock data into PostgreSQL.

Prerequisites:
  1. Phase 0 baseline completed
  2. Target PostgreSQL database created and reachable
  3. Alembic schema applied on target (this script can run upgrade)

Usage:
  .venv/bin/python -m scripts.migrate_sqlite_to_pg \\
      --source 'sqlite+aiosqlite:////path/to/bot.db' \\
      --target 'postgresql+asyncpg://pgclock:pgclock@127.0.0.1:5432/pgclock'
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
    p = argparse.ArgumentParser(description="SQLite → PostgreSQL data migration")
    p.add_argument("--source", required=True, help="SQLite DATABASE_URL")
    p.add_argument("--target", required=True, help="PostgreSQL DATABASE_URL (asyncpg)")
    p.add_argument("--skip-schema", action="store_true", help="Do not run alembic upgrade on target")
    p.add_argument("--allow-length-overflow", action="store_true")
    p.add_argument("--no-validate", action="store_true")
    args = p.parse_args()

    if not args.skip_schema:
        from app.db.alembic_runner import upgrade_head

        print("Applying Alembic migrations on target…", flush=True)
        upgrade_head(args.target)

    from app.db.sqlite_to_pg import migrate_sqlite_to_postgres

    def progress(step: str, payload: dict) -> None:
        print(f"[{step}] {json.dumps(payload, ensure_ascii=False)}", flush=True)

    result = migrate_sqlite_to_postgres(
        args.source,
        args.target,
        validate=not args.no_validate,
        allow_length_overflow=args.allow_length_overflow,
        progress=progress,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
