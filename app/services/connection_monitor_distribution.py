"""Download and extract the official, pinned connection-test Xray distribution."""

from __future__ import annotations

import hashlib
import platform
import secrets
import shutil
import stat
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.services.xray_probe_resources import MAX_BINARY_BYTES, XrayBinary


XRAY_VERSION = "26.3.27"
RELEASE_URL = f"https://github.com/XTLS/Xray-core/releases/download/v{XRAY_VERSION}"
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_NOTICE_BYTES = 1024 * 1024
DOWNLOAD_SECONDS = 90
NOTICE_FILES = ("LICENSE", "README.md")


class CoreInstallError(ValueError):
    """A fixed setup diagnostic without paths, credentials or remote payloads."""


@dataclass(frozen=True, slots=True)
class XrayDistribution:
    architecture: str
    archive_name: str
    archive_sha256: str
    binary_sha256: str

    @property
    def directory_name(self) -> str:
        return f"v{XRAY_VERSION}-{self.architecture}"


DISTRIBUTIONS = {
    "amd64": XrayDistribution("amd64", "Xray-linux-64.zip",
        "23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae",
        "8255dd939c34cf966cc91517b6324dd3c8d0bcf49ffac8beca049a38c46845ed"),
    "arm64": XrayDistribution("arm64", "Xray-linux-arm64-v8a.zip",
        "4d30283ae614e3057f730f67cd088a42be6fdf91f8639d82cb69e48cde80413c",
        "c2d20a7045250497083afea0d79db0672f6c89a25aaaf37c92de034d6b764b04"),
}
ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def select_distribution() -> XrayDistribution:
    architecture = ARCHITECTURES.get(platform.machine().lower())
    if platform.system() != "Linux" or architecture is None:
        raise CoreInstallError("unsupported_platform")
    return DISTRIBUTIONS[architecture]


def download_archive(client: httpx.Client, distribution: XrayDistribution, destination: Path) -> None:
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    digest, size = hashlib.sha256(), 0
    with client.stream("GET", f"{RELEASE_URL}/{distribution.archive_name}", headers={"Accept-Encoding": "identity"}) as response:
        response.raise_for_status()
        with destination.open("xb") as output:
            # Check each received chunk; buffering 64 KiB lets a slow peer hide the deadline.
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES or time.monotonic() > deadline:
                    raise CoreInstallError("download_limit")
                digest.update(chunk)
                output.write(chunk)
    if not secrets.compare_digest(digest.hexdigest(), distribution.archive_sha256):
        raise CoreInstallError("archive_checksum")


def _extract_member(archive: zipfile.ZipFile, name: str, destination: Path, *, maximum: int) -> None:
    try:
        entry = archive.getinfo(name)
    except KeyError:
        raise CoreInstallError("archive_contents") from None
    mode = entry.external_attr >> 16
    if entry.is_dir() or stat.S_ISLNK(mode) or not 0 < entry.file_size <= maximum:
        raise CoreInstallError("archive_contents")
    with archive.open(entry) as source, destination.open("xb") as output:
        shutil.copyfileobj(source, output, length=64 * 1024)
    destination.chmod(0o755 if name == "xray" else 0o644)


def stage_distribution(distribution: XrayDistribution, staging: Path) -> Path:
    archive_path = staging / "release.zip"
    with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=True, max_redirects=3) as client:
        download_archive(client, distribution, archive_path)
    payload = staging / "payload"
    payload.mkdir(mode=0o755)
    with zipfile.ZipFile(archive_path) as archive:
        _extract_member(archive, "xray", payload / "xray", maximum=MAX_BINARY_BYTES)
        for name in NOTICE_FILES:
            _extract_member(archive, name, payload / name, maximum=MAX_NOTICE_BYTES)
    XrayBinary(payload / "xray", distribution.binary_sha256).verify()
    return payload
