"""Provision an isolated Xray executable and merge its verified settings atomically."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.services.connection_monitor_distribution import (
    NOTICE_FILES, CoreInstallError, XrayDistribution, select_distribution, stage_distribution,
)
from app.services.xray_probe_resources import XrayBinary, XrayProbeError


PATH_KEY = "CONNECTION_MONITOR_XRAY_PATH"
HASH_KEY = "CONNECTION_MONITOR_XRAY_SHA256"
CORE_KEYS = (PATH_KEY, HASH_KEY)
ENV_PATTERN = re.compile(r"^[ \t]*(?:export\s+)?(CONNECTION_MONITOR_XRAY_PATH|CONNECTION_MONITOR_XRAY_SHA256)\s*=(.*)$", re.M)
MANAGED_DIRECTORY = ("data", "connection-monitor", "xray")


def _read_env(path: Path) -> tuple[str, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise CoreInstallError("env_file")
        return source.read(), info


def _configured_core(text: str) -> dict[str, str]:
    values = {}
    for match in ENV_PATTERN.finditer(text):
        try:
            parsed = shlex.split(match[2], comments=True)
        except ValueError:
            raise CoreInstallError("custom_configuration") from None
        if len(parsed) > 1:
            raise CoreInstallError("custom_configuration")
        values[match[1]] = parsed[0] if parsed else ""
    values.update({key: os.environ[key] for key in CORE_KEYS if key in os.environ})
    return values


def _write_core_settings(path: Path, binary: XrayBinary, *, expected: dict[str, str]) -> None:
    # Read again after download so unrelated settings changed in the meantime survive.
    text, info = _read_env(path)
    values = {PATH_KEY: str(binary.path), HASH_KEY: binary.sha256}
    current = _configured_core(text)
    if current != expected and current != values:
        raise CoreInstallError("configuration_changed")
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match[1]
        if key in seen:
            return ""
        seen.add(key)
        return f"{key}={json.dumps(values[key], ensure_ascii=False)}"

    updated = ENV_PATTERN.sub(replace, text)
    for key in CORE_KEYS:
        if key not in seen:
            updated = updated.rstrip("\n") + f"\n{key}={json.dumps(values[key], ensure_ascii=False)}\n"
    if updated == text:
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".env.xray-", delete=False) as output:
            temporary = Path(output.name)
            if os.geteuid() == 0:
                os.fchown(output.fileno(), info.st_uid, info.st_gid)
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _secure_directory(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        path.mkdir(mode=0o755)
        path.chmod(0o755)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o022:
        raise CoreInstallError("directory_permissions")


def _install_directory(root: Path) -> Path:
    directory = root
    for part in MANAGED_DIRECTORY:
        directory /= part
        _secure_directory(directory)
    return directory


@contextmanager
def _install_lock(directory: Path) -> Iterator[None]:
    descriptor = os.open(directory / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CoreInstallError("install_busy") from None
        yield


def _is_verified(binary: XrayBinary) -> bool:
    try:
        binary.verify()
    except XrayProbeError:
        return False
    return True


def _install_distribution(distribution: XrayDistribution, directory: Path) -> XrayBinary:
    destination = directory / distribution.directory_name
    _secure_directory(destination)
    binary = XrayBinary(destination / "xray", distribution.binary_sha256)
    if _is_verified(binary) and all((destination / name).is_file() and not (destination / name).is_symlink() for name in NOTICE_FILES):
        return binary
    with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as folder:
        payload = stage_distribution(distribution, Path(folder))
        for name in (*NOTICE_FILES, "xray"):
            os.replace(payload / name, destination / name)
    binary.verify()
    return binary


def ensure_monitor_core(root: Path) -> str:
    """Return managed/custom after verified installation; never enable connection tests."""
    root = root.resolve(strict=True)
    if "${" in str(root) or any(ord(character) < 32 or ord(character) == 127 for character in str(root)):
        raise CoreInstallError("install_path")
    text, _ = _read_env(root / ".env")
    configured = _configured_core(text)
    managed = root.joinpath(*MANAGED_DIRECTORY)
    path, digest = configured.get(PATH_KEY, ""), configured.get(HASH_KEY, "")
    is_managed = bool(path) and Path(path).is_relative_to(managed) and ".." not in Path(path).parts
    if any(key in os.environ for key in CORE_KEYS) or (path and not is_managed):
        if not _is_verified(XrayBinary(Path(path), digest)):
            raise CoreInstallError("custom_configuration")
        return "custom"
    if not path and digest:
        raise CoreInstallError("custom_configuration")
    distribution = select_distribution()
    directory = _install_directory(root)
    with _install_lock(directory):
        binary = _install_distribution(distribution, directory)
        _write_core_settings(root / ".env", binary, expected=configured)
    return "managed"
