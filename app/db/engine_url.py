"""Database URL helpers — engine detection and dialect conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, unquote


@dataclass(frozen=True)
class EngineInfo:
    dialect: str  # sqlite | postgresql
    url: str
    is_sqlite: bool
    is_postgresql: bool
    sqlite_path: Path | None = None
    pg_dsn: str | None = None  # libpq-style for pg_dump (sync)


def normalize_async_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("DATABASE_URL is empty")
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql://") and "+asyncpg" not in u.split("://", 1)[0]:
        u = "postgresql+asyncpg://" + u.split("://", 1)[1]
    if u.startswith("sqlite://") and "+aiosqlite" not in u.split("://", 1)[0]:
        # sqlite:///path → sqlite+aiosqlite:///path
        u = "sqlite+aiosqlite://" + u.split("://", 1)[1]
    return u


def to_sync_url(url: str) -> str:
    """Convert async SQLAlchemy URL to a sync driver URL (Alembic / pg tools)."""
    u = normalize_async_url(url)
    if u.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + u[len("sqlite+aiosqlite://") :]
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + u[len("postgresql+asyncpg://") :]
    return u


def parse_engine(url: str) -> EngineInfo:
    u = normalize_async_url(url)
    if u.startswith("sqlite"):
        path = _sqlite_path_from_url(u)
        return EngineInfo(
            dialect="sqlite",
            url=u,
            is_sqlite=True,
            is_postgresql=False,
            sqlite_path=path,
        )
    if u.startswith("postgresql"):
        return EngineInfo(
            dialect="postgresql",
            url=u,
            is_sqlite=False,
            is_postgresql=True,
            pg_dsn=_asyncpg_url_to_libpq(u),
        )
    raise ValueError(f"Unsupported DATABASE_URL dialect: {u.split(':', 1)[0]}")


def _sqlite_path_from_url(url: str) -> Path:
    # Match existing backup.sqlite_db_path semantics: everything after :/// 
    m = re.search(r":///(.+)$", url)
    if not m:
        raise ValueError(f"Cannot parse SQLite path from {url!r}")
    raw = m.group(1)
    if raw.startswith("/"):
        return Path(raw)
    from app.config import ROOT_DIR

    return (ROOT_DIR / raw).resolve()

def _asyncpg_url_to_libpq(url: str) -> str:
    """Build a libpq connection URI for pg_dump/pg_restore."""
    sync = to_sync_url(url)
    # postgresql+psycopg://user:pass@host:port/db → postgresql://...
    if sync.startswith("postgresql+psycopg://"):
        return "postgresql://" + sync[len("postgresql+psycopg://") :]
    if sync.startswith("postgresql+psycopg2://"):
        return "postgresql://" + sync[len("postgresql+psycopg2://") :]
    return sync


def pg_connection_parts(url: str) -> dict[str, str | int | None]:
    dsn = parse_engine(url).pg_dsn or ""
    parsed = urlparse(dsn)
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or "") if parsed.password is not None else None,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/").lstrip("/") or "pgclock",
    }
