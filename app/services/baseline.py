"""Phase 0 baseline — production backup + version record + restore verification."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.services.backup import (
    create_backup,
    sqlite_db_path,
    validate_backup_archive,
)
from app.services.updates import local_version
from app.version import __version__

log = logging.getLogger(__name__)

BASELINE_DIR = DATA_DIR / "baselines"
BASELINE_RECORD = "BASELINE.json"
# Always resolve git metadata from the installed project tree (not a temp ROOT_DIR).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def git_identity() -> dict[str, str]:
    """Record current git commit / branch (best-effort)."""
    out: dict[str, str] = {
        "commit": "",
        "branch": "",
        "describe": "",
        "status_short": "",
    }
    try:

        def _run(*args: str) -> str:
            r = subprocess.run(
                ["git", *args],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return (r.stdout or "").strip()

        out["commit"] = _run("rev-parse", "HEAD")
        out["branch"] = _run("rev-parse", "--abbrev-ref", "HEAD")
        out["describe"] = _run("describe", "--always", "--dirty", "--tags")
        out["status_short"] = _run("status", "--porcelain")
    except Exception as e:
        log.warning("git identity failed: %s", e)
    return out


def create_phase0_baseline(
    *,
    note: str = "phase0-pre-migration",
    verify_restore: bool = True,
) -> dict[str, Any]:
    """Create a complete pre-migration baseline under data/baselines/<id>/."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        BASELINE_DIR.chmod(0o700)
    except OSError:
        pass

    stamp = _utcnow_stamp()
    baseline_id = f"phase0-{stamp}"
    root = BASELINE_DIR / baseline_id
    root.mkdir(parents=True, exist_ok=False)
    try:
        root.chmod(0o700)
    except OSError:
        pass

    settings = get_settings()
    git = git_identity()

    backup = create_backup(
        note=note,
        include_env=True,
        created_by="phase0-baseline",
    )
    backup_zip = Path(backup["path"])
    baseline_zip = root / backup_zip.name
    shutil.copy2(backup_zip, baseline_zip)

    db_src = sqlite_db_path()
    db_dest = root / "bot.db"
    if db_src.is_file():
        from app.services.backup import _safe_copy_sqlite

        _safe_copy_sqlite(db_src, db_dest)
        db_meta: dict[str, Any] = {
            "path": "bot.db",
            "sha256": _sha256(db_dest),
            "size": db_dest.stat().st_size,
        }
    else:
        db_meta = {"path": "bot.db", "missing": True}

    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_files: list[dict[str, Any]] = []
    for rel, stored_as in ((".env", "env"), (".env.example", "env.example")):
        src = ROOT_DIR / rel
        if not src.is_file():
            continue
        dest = config_dir / stored_as
        shutil.copy2(src, dest)
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        config_files.append(
            {
                "name": rel,
                "stored_as": stored_as,
                "sha256": _sha256(dest),
                "size": dest.stat().st_size,
            }
        )

    web_admin = DATA_DIR / "web_admin.json"
    if web_admin.is_file():
        dest = config_dir / "web_admin.json"
        shutil.copy2(web_admin, dest)
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        config_files.append(
            {
                "name": "data/web_admin.json",
                "stored_as": "web_admin.json",
                "sha256": _sha256(dest),
                "size": dest.stat().st_size,
            }
        )

    record: dict[str, Any] = {
        "magic": "pgclock-phase0-baseline-v1",
        "baseline_id": baseline_id,
        "created_at": _now_iso(),
        "note": note,
        "app_version": local_version() or __version__,
        "module_version": __version__,
        "git": git,
        "database_url_dialect": (
            "postgresql"
            if "postgresql" in (settings.database_url or "")
            else "sqlite"
            if "sqlite" in (settings.database_url or "")
            else "unknown"
        ),
        "sqlite_db_path": str(db_src),
        "backup": {
            "id": backup.get("id"),
            "filename": baseline_zip.name,
            "sha256": backup.get("sha256"),
            "size": backup.get("size"),
            "file_count": backup.get("file_count"),
            "include_env": backup.get("include_env"),
        },
        "sqlite_copy": db_meta,
        "config_files": config_files,
        "restore_verification": None,
    }

    if verify_restore:
        record["restore_verification"] = verify_restore_procedure(baseline_zip)

    (root / BASELINE_RECORD).write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        (root / BASELINE_RECORD).chmod(0o600)
        baseline_zip.chmod(0o600)
    except OSError:
        pass

    (BASELINE_DIR / "LATEST").write_text(baseline_id + "\n", encoding="utf-8")

    ok = True
    if verify_restore and not (record["restore_verification"] or {}).get("ok"):
        ok = False

    return {
        "ok": ok,
        "baseline_id": baseline_id,
        "path": str(root),
        "record": record,
    }


def verify_restore_procedure(zip_path: Path) -> dict[str, Any]:
    """Validate archive and dry-restore into a temporary directory (live data untouched)."""
    ok, err, manifest = validate_backup_archive(zip_path)
    result: dict[str, Any] = {
        "ok": False,
        "validated": ok,
        "validate_error": err if not ok else "",
        "checked_at": _now_iso(),
        "sqlite_ok": False,
        "tables_sample": {},
        "has_web_admin": False,
        "has_env": False,
    }
    if not ok or not manifest:
        return result

    with tempfile.TemporaryDirectory(prefix="pgclock-phase0-restore-") as tmp:
        extract = Path(tmp) / "extract"
        extract.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract)

        db_path = extract / "data" / "bot.db"
        if not db_path.is_file():
            pg_dump = extract / "data" / "postgres.dump"
            if pg_dump.is_file():
                result["ok"] = True
                result["engine"] = "postgresql"
                result["postgres_dump_size"] = pg_dump.stat().st_size
                return result
            result["validate_error"] = "no database artifact in archive"
            return result

        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            sample: dict[str, int] = {}
            for t in ("bot_users", "settings", "orders", "reseller_profiles", "pg_staff_access"):
                if t in tables:
                    sample[t] = int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
            result["tables_sample"] = sample
            result["sqlite_ok"] = True
            result["engine"] = "sqlite"
        finally:
            conn.close()

        result["has_web_admin"] = (extract / "data" / "web_admin.json").is_file()
        result["has_env"] = (extract / "env" / ".env").is_file()
        result["manifest_magic"] = manifest.get("magic")
        result["manifest_version"] = manifest.get("app_version")
        result["ok"] = True
    return result


def latest_baseline() -> dict[str, Any] | None:
    latest = BASELINE_DIR / "LATEST"
    if not latest.is_file():
        return None
    bid = latest.read_text(encoding="utf-8").strip()
    record_path = BASELINE_DIR / bid / BASELINE_RECORD
    if not record_path.is_file():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))
