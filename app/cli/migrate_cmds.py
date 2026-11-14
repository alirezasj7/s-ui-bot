"""pgclock migrate — Alembic upgrade / optional SQLite→PostgreSQL ETL."""

from __future__ import annotations

from app.cli.context import CliContext, database_url, require_confirm
from app.cli.output import CliError, header, info, kv, ok, warn


def cmd_migrate(
    ctx: CliContext,
    *,
    from_sqlite: bool = False,
    source: str = "",
    target: str = "",
    yes: bool = False,
    skip_schema: bool = False,
) -> int:
    """Default: alembic upgrade head on configured DATABASE_URL.

    With --from-sqlite: run offline ETL (does not change default DB behavior).
    """
    header("migrate")
    if from_sqlite:
        return _migrate_sqlite_to_pg(
            ctx,
            source=source,
            target=target,
            yes=yes,
            skip_schema=skip_schema,
        )

    url = database_url(ctx.root)
    kv("database_url", _redact(url))
    from app.db.alembic_runner import current_revision, upgrade_head

    before = current_revision(url)
    kv("revision_before", before or "(none)")
    upgrade_head(url)
    after = current_revision(url)
    ok(f"upgraded to {after}")
    return 0


def _migrate_sqlite_to_pg(
    ctx: CliContext,
    *,
    source: str,
    target: str,
    yes: bool,
    skip_schema: bool,
) -> int:
    src = (source or "").strip()
    dst = (target or "").strip()
    if not src or not dst:
        raise CliError(
            "Usage: pgclock migrate --from-sqlite "
            "--source 'sqlite+aiosqlite:///…' "
            "--target 'postgresql+asyncpg://…'"
        )
    require_confirm(
        "Run SQLite→PostgreSQL data migration? Target tables will be truncated.",
        yes=yes,
    )
    if not skip_schema:
        info("Applying Alembic schema on target…")
        from app.db.alembic_runner import upgrade_head

        upgrade_head(dst)

    from app.db.sqlite_to_pg import migrate_sqlite_to_postgres

    def progress(step: str, payload: dict) -> None:
        info(f"{step}: {payload}")

    result = migrate_sqlite_to_postgres(src, dst, validate=True, progress=progress)
    if not result.ok:
        for e in result.errors:
            warn(e)
        raise CliError("Migration failed")
    ok("SQLite→PostgreSQL migration complete")
    kv("tables", len(result.tables_copied))
    return 0


def _redact(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.rsplit("@", 1)
    if ":" in creds:
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://***@{host}"
