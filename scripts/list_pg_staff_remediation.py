#!/usr/bin/env python3
"""Phase D3 — read-only inventory of pg_staff remediation cohorts.

Usage:
  .venv/bin/python -m scripts.list_pg_staff_remediation
  .venv/bin/python -m scripts.list_pg_staff_remediation --json
  .venv/bin/python -m scripts.list_pg_staff_remediation --needs-remediation

Never prints passwords or encrypted blobs. Does not write to the database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _run(*, needs_only: bool, as_json: bool) -> int:
    from app.db.session import SessionLocal
    from app.services.pg_staff_access import inventory_staff_remediation

    async with SessionLocal() as session:
        rows = await inventory_staff_remediation(session)

    if needs_only:
        rows = [r for r in rows if r.get("needs_remediation")]

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("No pg_staff rows" + (" needing remediation" if needs_only else "") + ".")
        return 0

    headers = (
        "cohort",
        "id",
        "pg_username",
        "web_username",
        "active",
        "enc_ready",
        "aligned",
        "needs_fix",
    )
    print("\t".join(headers))
    for r in rows:
        print(
            "\t".join(
                [
                    str(r.get("cohort") or ""),
                    str(r.get("id") or ""),
                    str(r.get("pg_username") or ""),
                    str(r.get("web_username") or ""),
                    "1" if r.get("is_active") else "0",
                    "1" if r.get("credentials_ready") else "0",
                    "1" if r.get("username_aligned") else "0",
                    "1" if r.get("needs_remediation") else "0",
                ]
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List pg_staff remediation cohorts (read-only)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of TSV",
    )
    parser.add_argument(
        "--needs-remediation",
        action="store_true",
        help="Only rows with missing enc or username mismatch",
    )
    args = parser.parse_args()
    return asyncio.run(_run(needs_only=args.needs_remediation, as_json=args.json))


if __name__ == "__main__":
    raise SystemExit(main())
