"""PGClock global CLI — resolve install root from any working directory."""

from __future__ import annotations

import os
from pathlib import Path

MARKER_NAME = "install_root"
LIB_DIR = Path("/usr/local/lib/pgclockbot")
MARKER_PATH = LIB_DIR / MARKER_NAME
BIN_PATH = Path("/usr/local/bin/pgclock")


class InstallRootError(RuntimeError):
    pass


def _looks_like_install(root: Path) -> bool:
    return (
        root.is_dir()
        and (root / "run.py").is_file()
        and (root / "app").is_dir()
        and ((root / ".venv" / "bin" / "python").is_file() or (root / "requirements.txt").is_file())
    )


def read_marker() -> Path | None:
    try:
        if not MARKER_PATH.is_file():
            return None
        raw = MARKER_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        if _looks_like_install(path):
            return path
    except OSError:
        return None
    return None


def resolve_install_root(*, explicit: str | None = None) -> Path:
    """Find the PGClockBot install directory.

    Order:
    1. --root / PGCLOCK_HOME / PGCLOCK_ROOT
    2. /usr/local/lib/pgclockbot/install_root marker
    3. Walk parents of this package (dev / in-tree runs)
    4. Common paths under $HOME
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for key in ("PGCLOCK_HOME", "PGCLOCK_ROOT", "PGCLOCKBOT_HOME"):
        val = (os.environ.get(key) or "").strip()
        if val:
            candidates.append(Path(val).expanduser())

    marked = read_marker()
    if marked is not None:
        candidates.append(marked)

    # In-tree: app/cli/install_root.py → parents[2] = repo root
    here = Path(__file__).resolve()
    candidates.append(here.parents[2])

    home = Path.home()
    for name in ("PGClockBot", "pgclockbot", "pgclock"):
        candidates.append(home / name)
        candidates.append(Path("/opt") / name)
        candidates.append(Path("/srv") / name)

    seen: set[Path] = set()
    for raw in candidates:
        try:
            path = raw.resolve()
        except OSError:
            continue
        if path in seen:
            continue
        seen.add(path)
        if _looks_like_install(path):
            return path

    raise InstallRootError(
        "Could not locate PGClockBot install root. "
        "Set PGCLOCK_HOME, or reinstall the global CLI "
        "(sudo bash scripts/install_global_cli.sh)."
    )


def python_bin(root: Path) -> Path:
    venv_py = root / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return venv_py
    return Path(os.environ.get("PYTHON_BIN") or "python3")


def write_install_marker(root: Path) -> Path:
    """Write install_root marker (caller must have privileges for /usr/local)."""
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(str(root.resolve()) + "\n", encoding="utf-8")
    try:
        MARKER_PATH.chmod(0o644)
    except OSError:
        pass
    return MARKER_PATH
