"""Phase C2 — write authorization: no owner mutation fallback."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pasarguard import PasarGuardError


class StaffPgWriteClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_owner_client(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        owner = {
            "role": "admin",
            "web_owner": True,
            "pg_is_owner": True,
            "org_principal_id": 1,
            "org_depth": 0,
            "org_parent_id": None,
            "org_status": "active",
        }
        with patch("app.api.pg_pages.get_pg", return_value=fake):
            client, as_owner = await _staff_pg(AsyncMock(), owner)
        self.assertTrue(as_owner)
        self.assertIs(client, fake)
        with self.assertRaises(PasarGuardError):
            await _staff_pg(AsyncMock(), {"role": "admin", "pg_is_owner": True})

    async def test_limited_admin_env_client_not_as_owner(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        hybrid = {
            "role": "admin",
            "web_owner": True,
            "pg_is_owner": False,
            "org_principal_id": 1,
            "org_depth": 0,
            "org_parent_id": None,
            "org_status": "active",
        }
        with patch("app.api.pg_pages.get_pg", return_value=fake):
            client, as_owner = await _staff_pg(AsyncMock(), hybrid)
        self.assertFalse(as_owner)
        self.assertIs(client, fake)

    async def test_reseller_own_client(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        with patch(
            "app.api.pg_pages.get_pg_for_reseller",
            new=AsyncMock(return_value=fake),
        ):
            client, as_owner = await _staff_pg(
                AsyncMock(),
                {"role": "reseller", "bot_user_id": 7, "pg_admin_username": "r"},
            )
        self.assertFalse(as_owner)
        self.assertIs(client, fake)

    async def test_pg_staff_fail_closed_without_credentials(self):
        from app.api.pg_pages import _staff_pg

        with (
            patch("app.api.pg_pages.get_pg") as gp,
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(
                    side_effect=PasarGuardError("رمز پاسارگارد برای این حساب ذخیره نشده")
                ),
            ),
        ):
            with self.assertRaises(PasarGuardError) as ctx:
                await _staff_pg(
                    AsyncMock(),
                    {"role": "pg_staff", "pg_admin_username": "s1"},
                )
        gp.assert_not_called()
        self.assertIn("ذخیره نشده", str(ctx.exception))

    async def test_pg_staff_uses_own_client_when_credentialed(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        with (
            patch("app.api.pg_pages.get_pg") as gp,
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(return_value=fake),
            ),
        ):
            client, as_owner = await _staff_pg(
                AsyncMock(),
                {
                    "role": "pg_staff",
                    "pg_admin_username": "s1",
                    "pg_staff_id": 2,
                },
            )
        self.assertFalse(as_owner)
        self.assertIs(client, fake)
        gp.assert_not_called()


class AssertOwnedUserWritePreludeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pg_staff_returns_none_without_credentials(self):
        from app.api.pg_pages import _assert_owned_user

        owner = AsyncMock()
        owner.get_user_by_id = AsyncMock(return_value={"id": 1, "admin": "s1"})
        with (
            patch("app.api.pg_pages.get_pg", return_value=owner),
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(side_effect=PasarGuardError("no creds")),
            ),
        ):
            out = await _assert_owned_user(
                {"role": "pg_staff", "pg_admin_username": "s1"},
                1,
                session=AsyncMock(),
            )
        self.assertIsNone(out)
        owner.get_user_by_id.assert_not_awaited()


class ExactActionSourceGuards(unittest.TestCase):
    def test_mutations_gate_exact_actions(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        for needle in (
            'staff_pg_action(staff, "templates", "create")',
            'staff_pg_action(staff, "templates", "delete")',
            'staff_pg_action(staff, "groups", "create")',
            'staff_pg_action(staff, "hosts", "create")',
            'staff_pg_action(staff, "nodes", "reconnect")',
        ):
            self.assertIn(needle, src)

    def test_staff_pg_no_pg_staff_owner_return(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertIn("بدون اعتبارنامه اختصاصی", fn)
        # Platform-admin uses env client; as_owner only when pg_is_owner (Hybrid)
        self.assertIn("return get_pg(), bool(staff.get(\"pg_is_owner\"))", fn)
        self.assertEqual(fn.count("return get_pg(), True"), 0)
        self.assertIn("get_pg_for_staff", fn)
        self.assertIn('staff.get("role") == "pg_staff"', fn)


if __name__ == "__main__":
    unittest.main()
