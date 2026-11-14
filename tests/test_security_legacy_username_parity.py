"""Legacy /security/username must match /security/credentials PG-username rules.

Phase D documented debt: reseller could rename web login away from pg_admin_username
via the back-compat POST /security/username route. Harden to parity with credentials.
"""

from __future__ import annotations

import unittest
from pathlib import Path


class LegacyUsernameRouteParityTests(unittest.TestCase):
    def test_legacy_route_still_registered(self):
        src = Path("app/api/security.py").read_text(encoding="utf-8")
        self.assertIn('@app.post("/security/username")', src)
        self.assertIn("async def security_change_username_legacy", src)

    def test_legacy_reseller_enforces_pg_username_equality(self):
        src = Path("app/api/security.py").read_text(encoding="utf-8")
        legacy = src[
            src.find("async def security_change_username_legacy") : src.find(
                "async def security_change_password_legacy"
            )
        ]
        self.assertIn("pg_admin_username", legacy)
        self.assertIn("نام کاربری باید همان یوزر پاسارگارد باشد", legacy)
        # Must not assign web_username before the PG equality guard.
        pg_guard = legacy.find("pg_admin_username")
        assign = legacy.find("profile.web_username = cleaned")
        self.assertGreater(pg_guard, 0)
        self.assertGreater(assign, pg_guard)

    def test_legacy_owner_checks_username_collisions(self):
        src = Path("app/api/security.py").read_text(encoding="utf-8")
        legacy = src[
            src.find("async def security_change_username_legacy") : src.find(
                "async def security_change_password_legacy"
            )
        ]
        self.assertIn("PgStaffAccess", legacy)
        self.assertIn("این نام کاربری قبلاً برای یک نماینده گرفته شده", legacy)
        self.assertIn(
            "این نام کاربری قبلاً برای دسترسی وب ادمین پاسارگارد گرفته شده",
            legacy,
        )

    def test_credentials_path_still_has_equality_guard(self):
        src = Path("app/api/security.py").read_text(encoding="utf-8")
        creds = src[
            src.find("async def security_change_credentials") : src.find(
                "async def security_change_username_legacy"
            )
        ]
        self.assertIn("نام کاربری باید همان یوزر پاسارگارد باشد", creds)


if __name__ == "__main__":
    unittest.main()
