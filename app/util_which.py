"""Shared PATH-safe binary lookup (systemd often has a short PATH)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

EXTRA_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Back-compat alias for older imports
_EXTRA_PATH = EXTRA_PATH


def which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    expanded = os.environ.get("PATH") or ""
    if EXTRA_PATH not in expanded:
        found = shutil.which(name, path=f"{expanded}:{EXTRA_PATH}" if expanded else EXTRA_PATH)
        if found:
            return found
    for prefix in ("/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin"):
        candidate = Path(prefix) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def env_with_path(**extra: str) -> dict[str, str]:
    """Copy os.environ with a PATH that still finds system binaries under systemd."""
    env = dict(os.environ)
    path = env.get("PATH") or ""
    if EXTRA_PATH not in path:
        env["PATH"] = f"{EXTRA_PATH}:{path}" if path else EXTRA_PATH
    env.update(extra)
    return env
