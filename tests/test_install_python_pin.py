"""Installer pins CPython 3.10–3.12 for the panel venv (avoid 3.13+ source builds)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "pgclock.sh"


class InstallPythonPinTests(unittest.TestCase):
    def test_prefers_python312_candidates(self):
        src = SH.read_text(encoding="utf-8")
        self.assertIn("_python_is_supported", src)
        self.assertIn("python3.12", src)
        self.assertIn("python3.11", src)
        self.assertIn("python3.10", src)
        # Preference order in ensure_python
        block = src.split("ensure_python() {", 1)[1].split("ensure_venv() {", 1)[0]
        self.assertIn("candidates=(python3.12 python3.11 python3.10)", block)
        self.assertIn("_try_apt_install_python312", block)
        self.assertIn("3.10–3.12", block)
        self.assertIn("3.13+", block)
        # Newer Ubuntu often lacks python3.12 in the default archive.
        self.assertIn("deadsnakes", src)
        try_block = src.split("_try_apt_install_python312() {", 1)[1].split(
            "ensure_python() {", 1
        )[0]
        self.assertIn("ppa:deadsnakes/ppa", try_block)
        # Must not hide apt failures (was the silent 3.14 install break).
        self.assertNotIn("apt-get install -y python3.12 python3.12-venv >/dev/null", try_block)

    def test_recreates_unsupported_venv(self):
        src = SH.read_text(encoding="utf-8")
        venv = src.split("ensure_venv() {", 1)[1].split("service_installed() {", 1)[0]
        self.assertIn("unsupported", venv.lower())
        self.assertIn("rm -rf .venv", venv)
        self.assertIn("Installing Python packages", venv)
        # Quiet pip was the “stuck after venv” illusion on small VPS.
        self.assertNotIn(
            "pip install -r requirements.txt -q",
            venv,
        )


if __name__ == "__main__":
    unittest.main()
