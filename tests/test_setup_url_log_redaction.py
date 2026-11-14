"""Regression test: the one-time setup-wizard URL (which carries the gate
token as a query parameter) must never be written to logs.

Previously ``app/main.py`` did ``logger.warning("... %s", setup_url)`` where
``setup_url`` is the *exact* URL already persisted to a chmod-0600 hint file
by ``persist_setup_entry_url()``. Logs are frequently shipped to broader-read
locations (journald, log aggregators, `docker logs`, etc.) than that
protected file, so this leaked the setup bypass token to anyone who could
read logs within its 15-minute validity window.

This is checked structurally (AST), not by a brittle full-source string
match: we find the ``logger.warning`` call inside the "first run" branch and
assert its arguments never reference the ``setup_url`` variable, while still
referencing the protected hint file path.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


class SetupUrlLogRedactionTests(unittest.TestCase):
    def _find_first_run_warning_call(self) -> ast.Call:
        src = Path("app/main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            # Look for `if not creds.get("password") or not is_setup_complete():`
            test_src = ast.dump(node.test)
            if "creds" not in test_src or "password" not in test_src:
                continue
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "warning"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "logger"
                ):
                    return sub
        raise AssertionError(
            "could not locate the first-run setup logger.warning(...) call "
            "in app/main.py — update this test if that code moved"
        )

    def test_warning_call_never_interpolates_the_raw_setup_url(self):
        call = self._find_first_run_warning_call()
        referenced_names = {
            n.id
            for arg in call.args
            for n in ast.walk(arg)
            if isinstance(n, ast.Name)
        }
        self.assertNotIn(
            "setup_url",
            referenced_names,
            "the raw setup_url (contains the one-time gate token) must not "
            "be passed to logger.warning(...)",
        )

    def test_warning_call_points_to_the_protected_hint_file_instead(self):
        call = self._find_first_run_warning_call()
        referenced_names = {
            n.id
            for arg in call.args
            for n in ast.walk(arg)
            if isinstance(n, ast.Name)
        }
        self.assertIn("SETUP_ENTRY_FILE", referenced_names)


if __name__ == "__main__":
    unittest.main()
