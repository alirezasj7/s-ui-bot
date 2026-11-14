"""SQLite → PostgreSQL offline data migration (ETL).

This is a one-shot cutover tool — not a dual-runtime database path.
Production runtime uses a single ``DATABASE_URL`` (PostgreSQL recommended).
SQLite remains available for labs and as the ETL source for existing installs.

Preserves primary keys, copies all application tables in FK-safe order,
resets PostgreSQL sequences, and optionally validates row counts.

CLI: ``pgclock migrate --from-sqlite --source … --target …``
Docs: ``docs/PHASE_A_DATABASE.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db.engine_url import parse_engine, to_sync_url
from app.db.validate import TABLE_ORDER, ValidationReport, compare_databases, scan_varchar_overflows

log = logging.getLogger(__name__)

ProgressCB = Callable[[str, dict[str, Any]], None]


@dataclass
class MigrationResult:
    ok: bool
    tables_copied: dict[str, int] = field(default_factory=dict)
    skipped_tables: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation: ValidationReport | None = None
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tables_copied": self.tables_copied,
            "skipped_tables": self.skipped_tables,
            "errors": self.errors,
            "validation": self.validation.to_dict() if self.validation else None,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _engine(url: str) -> Engine:
    return create_engine(to_sync_url(url))


def migrate_sqlite_to_postgres(
    source_url: str,
    target_url: str,
    *,
    validate: bool = True,
    allow_length_overflow: bool = False,
    progress: ProgressCB | None = None,
) -> MigrationResult:
    def emit(step: str, **kw: Any) -> None:
        if progress:
            progress(step, kw)
        log.info("migrate %s %s", step, kw)

    src_info = parse_engine(source_url)
    dst_info = parse_engine(target_url)
    if not src_info.is_sqlite:
        raise ValueError("source_url must be SQLite")
    if not dst_info.is_postgresql:
        raise ValueError("target_url must be PostgreSQL")

    result = MigrationResult(ok=False, started_at=_now())
    src = _engine(source_url)
    dst = _engine(target_url)
    try:
        emit("precheck")
        overflows = scan_varchar_overflows(src)
        if overflows and not allow_length_overflow:
            result.errors.append(
                f"VARCHAR overflows on source ({len(overflows)}); "
                "fix data or pass allow_length_overflow=True"
            )
            result.finished_at = _now()
            return result

        insp = inspect(dst)
        missing = [t for t in TABLE_ORDER if not insp.has_table(t)]
        if missing:
            result.errors.append(
                f"target schema missing tables: {missing}; run alembic upgrade head first"
            )
            result.finished_at = _now()
            return result

        # Wipe target once (reverse FK order) so per-table CASCADE cannot
        # destroy rows already copied earlier in the loop.
        emit("truncate_target")
        with dst.begin() as conn:
            for name in reversed(TABLE_ORDER):
                if insp.has_table(name):
                    conn.execute(text(f"TRUNCATE TABLE {name} CASCADE"))

        src_insp = inspect(src)
        copied: list[str] = []
        for name in TABLE_ORDER:
            if not src_insp.has_table(name):
                result.skipped_tables.append(name)
                emit("skip", table=name)
                continue
            emit("copy", table=name)
            n = _copy_table(src, dst, name, truncate=False)
            result.tables_copied[name] = n
            copied.append(name)

        emit("sequences")
        _reset_sequences(dst, copied)

        if validate:
            emit("validate")
            report = compare_databases(source_url, target_url)
            result.validation = report
            if not report.ok:
                result.errors.extend(report.mismatches)
                result.finished_at = _now()
                return result

        result.ok = True
        result.finished_at = _now()
        emit("done", tables=len(result.tables_copied))
        return result
    except Exception as e:
        log.exception("sqlite→pg migration failed")
        result.errors.append(str(e))
        result.finished_at = _now()
        return result
    finally:
        src.dispose()
        dst.dispose()


def _copy_table(
    src: Engine,
    dst: Engine,
    table_name: str,
    *,
    batch_size: int = 500,
    truncate: bool = True,
) -> int:
    src_meta = MetaData()
    dst_meta = MetaData()
    src_table = Table(table_name, src_meta, autoload_with=src)
    dst_table = Table(table_name, dst_meta, autoload_with=dst)

    src_cols = [c.name for c in src_table.columns]
    dst_cols = {c.name for c in dst_table.columns}
    cols = [c for c in src_cols if c in dst_cols]
    if not cols:
        return 0

    col_list = ", ".join(cols)
    with src.connect() as sconn, dst.begin() as dconn:
        if truncate:
            dconn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
        result = sconn.execute(text(f"SELECT {col_list} FROM {table_name}"))
        total = 0
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            payload = [dict(row._mapping) for row in rows]
            if payload:
                dconn.execute(dst_table.insert(), payload)
            total += len(payload)
    return total


def _reset_sequences(dst: Engine, tables: list[str]) -> None:
    """Align PostgreSQL serial sequences with MAX(id)."""
    with dst.begin() as conn:
        for name in tables:
            row = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"),
                {"t": name},
            ).scalar()
            if not row:
                continue
            conn.execute(
                text(
                    f"SELECT setval(:seq, COALESCE((SELECT MAX(id) FROM {name}), 1), "
                    f"COALESCE((SELECT MAX(id) FROM {name}), 0) > 0)"
                ),
                {"seq": row},
            )
