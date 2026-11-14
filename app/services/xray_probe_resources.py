"""Restricted files, trusted binaries and temporary loopback port reservations."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.py_compat import file_digest
from app.services.connection_monitor_config import MonitorBinding, build_monitor_config
from app.services.connection_monitor_types import MAX_MONITOR_ENDPOINTS, MonitorEndpoint

XRAY_VERSION = "26.3.27"
MAX_BINARY_BYTES = 100 * 1024 * 1024


class XrayProbeError(ValueError):
    """A fixed diagnostic code, never core output or configuration contents."""


@dataclass(frozen=True, slots=True)
class XrayBinary:
    path: Path
    sha256: str

    def verify(self) -> Path:
        if not self.path.is_absolute() or self.path.is_symlink():
            raise XrayProbeError("core_binary")
        try:
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(self.path, os.X_OK):
                raise XrayProbeError("core_binary")
            if self.path.parent.stat().st_mode & 0o022:
                raise XrayProbeError("core_binary")
            if info.st_size > MAX_BINARY_BYTES or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
                raise XrayProbeError("core_checksum")
            with self.path.open("rb") as source:
                actual = file_digest(source, "sha256").hexdigest()
        except OSError:
            raise XrayProbeError("core_binary") from None
        if not secrets.compare_digest(actual, self.sha256):
            raise XrayProbeError("core_checksum")
        return self.path


@dataclass(slots=True)
class ProbeResources:
    folder: tempfile.TemporaryDirectory[str] = field(repr=False)
    bindings: tuple[MonitorBinding, ...]
    config_path: Path = field(repr=False)
    reservations: list[socket.socket] = field(repr=False)

    def release_ports(self) -> None:
        for reservation in self.reservations:
            reservation.close()
        self.reservations.clear()

    def close(self) -> None:
        self.release_ports()
        self.folder.cleanup()


def _open_private_config(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)


def prepare_resources(endpoints: tuple[MonitorEndpoint, ...]) -> ProbeResources:
    if not endpoints or len(endpoints) > MAX_MONITOR_ENDPOINTS:
        raise XrayProbeError("core_capacity")
    folder = tempfile.TemporaryDirectory(prefix="pgclock-probe-")
    resources = ProbeResources(folder, (), Path(folder.name) / "config.json", [])
    try:
        for endpoint in endpoints:
            reservation = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            resources.reservations.append(reservation)
            reservation.bind(("127.0.0.1", 0))
            resources.bindings += (MonitorBinding(endpoint, reservation.getsockname()[1]),)
        config = build_monitor_config(resources.bindings)
        # The pinned core emits its startup marker only after every feature starts.
        config["log"] = {"loglevel": "warning", "access": "none"}
        with open(resources.config_path, "x", encoding="utf-8", opener=_open_private_config) as destination:
            json.dump(config, destination, separators=(",", ":"))
        return resources
    except BaseException:
        resources.close()
        raise
