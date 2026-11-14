"""Sidebar accordion rules (web panel and bot open together, PasarGuard exclusive)."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NavAccordionRulesTests(unittest.TestCase):
    def test_node_rules(self):
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "tests/nav_accordion.test.cjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Nav accordion rules", result.stdout)


if __name__ == "__main__":
    unittest.main()
