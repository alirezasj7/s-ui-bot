"""pgclock doctor reports when the Web Owner login and ADMIN_IDS disagree."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.cli.doctor_cmds import _owner_identity_status


def _status(password: str, admin_ids: list[int]) -> tuple[str, str, str]:
    with (
        patch("app.services.web_auth.load_web_admin", return_value={"password": password}),
        patch("app.config.get_settings", return_value=SimpleNamespace(admin_ids=admin_ids)),
    ):
        return _owner_identity_status()


class OwnerIdentityStatusTests(unittest.TestCase):
    def test_both_configured_is_ok(self):
        self.assertEqual(_status("hash", [1])[0], "OK")

    def test_web_owner_without_admin_ids_warns_about_telegram_tools(self):
        status, detail, fix = _status("hash", [])
        self.assertEqual(status, "WARN")
        self.assertIn("ADMIN_IDS is empty", detail)
        self.assertIn("ADMIN_IDS", fix)

    def test_admin_ids_without_web_password_warns_about_panel_login(self):
        status, detail, _ = _status("  ", [1])
        self.assertEqual(status, "WARN")
        self.assertIn("Web Owner password is empty", detail)

    def test_nothing_configured_warns(self):
        self.assertEqual(_status("", [])[0], "WARN")


if __name__ == "__main__":
    unittest.main()
