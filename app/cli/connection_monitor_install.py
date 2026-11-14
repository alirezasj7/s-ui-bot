"""Install or repair the connection-test core without changing monitoring preferences."""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from pathlib import Path

import httpx

from app.services.connection_monitor_distribution import CoreInstallError
from app.services.connection_monitor_install import ensure_monitor_core
from app.services.xray_probe_resources import XrayProbeError


logger = logging.getLogger(__name__)
ERROR_MESSAGES = {
    "unsupported_platform": "Automatic Xray setup supports Linux amd64 and arm64. Existing manual configuration is supported.",
    "custom_configuration": "Existing manual Xray configuration is incomplete or invalid; it was kept. Check it or clear both Xray settings before retrying.",
    "directory_permissions": "The Xray installation directory must not be a symlink or writable by group/other.",
    "install_busy": "Another Xray setup is running; retry when it finishes.",
    "configuration_changed": "Xray settings changed during setup; they were kept. Retry to use the current settings.",
    "install_path": "The installation directory cannot contain control characters or dotenv variable placeholders.",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        mode = ensure_monitor_core(args.root)
    except (CoreInstallError, XrayProbeError, OSError, httpx.HTTPError, zipfile.BadZipFile) as exc:
        logger.warning("Connection-test core setup failed error_type=%s", type(exc).__name__)
        message = ERROR_MESSAGES.get(str(exc), "Xray setup could not finish. Existing configuration was kept; retry setup after checking network access and file permissions.")
        print(message, file=sys.stderr)
        return 1
    print("Verified manual Xray configuration kept." if mode == "custom" else "Connection-test Xray is installed and configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
