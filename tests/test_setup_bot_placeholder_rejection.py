"""Regression test: POST /setup/bot must reject placeholder/example bot tokens.

Before the fix, ``setup_bot`` only checked the token for emptiness, so a
first-run operator could paste the documented example token
(``123456:ABC-DEF``) straight from the README and "complete" setup with a
non-functional bot — a subtle foot-gun that also weakens the setup gate's
guarantee that a real bot is wired up. ``is_placeholder_bot_token`` already
existed elsewhere but wasn't consulted here.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.services.security_policy import is_placeholder_bot_token


class SetupBotPlaceholderRejectionTests(unittest.TestCase):
    """Structural check: setup_bot must call is_placeholder_bot_token(token)."""

    def _setup_bot_source(self) -> str:
        tree = ast.parse(Path("app/api/app.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup_bot":
                return ast.unparse(node)
        raise AssertionError("setup_bot function not found in app/api/app.py")

    def test_setup_bot_checks_placeholder_before_persisting(self):
        body = self._setup_bot_source()
        self.assertIn("is_placeholder_bot_token", body)

        # Must reject *before* the token is ever written to disk.
        check_pos = body.index("is_placeholder_bot_token")
        persist_pos = body.index("update_env_keys")
        self.assertLess(
            check_pos,
            persist_pos,
            "is_placeholder_bot_token must be checked before update_env_keys persists the token",
        )

    def test_known_example_tokens_are_flagged(self):
        # Same values documented in README / .env.example — must never pass.
        for example in ("123456:ABC-DEF", "YOUR_BOT_TOKEN", "", "0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"):
            self.assertTrue(is_placeholder_bot_token(example), f"expected {example!r} to be flagged as placeholder")

    def test_realistic_token_is_not_flagged(self):
        self.assertFalse(is_placeholder_bot_token("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"))


if __name__ == "__main__":
    unittest.main()
