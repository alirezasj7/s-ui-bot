"""Guards: one web-panel login path per PasarGuard admin."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class ConflictGrantTests(unittest.IsolatedAsyncioTestCase):
    async def test_grant_blocked_when_reseller_has_web(self):
        from app.services.pg_staff_access import conflict_message_for_new_grant

        reseller = SimpleNamespace(
            id=1,
            user_id=10,
            web_username="shop1",
            web_password_hash="x",
            is_active=True,
            setup_completed_at="yes",
            pg_admin_username="PgAdmin1",
        )
        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.reseller_by_pg_username",
                new=AsyncMock(return_value=reseller),
            ),
            patch(
                "app.services.pg_staff_access.load_web_admin",
                return_value={"username": "owner"},
            ),
            patch(
                "app.services.resellers.setup_is_complete",
                return_value=True,
            ),
        ):
            msg = await conflict_message_for_new_grant(AsyncMock(), "pgadmin1")
        self.assertIsNotNone(msg)
        self.assertIn("نماینده", msg)
        self.assertIn("shop1", msg)

    async def test_grant_blocked_when_staff_exists(self):
        from app.services.pg_staff_access import conflict_message_for_new_grant

        staff = SimpleNamespace(
            id=5,
            web_username="staff1",
            pg_username="pg_x",
            is_active=True,
            note=None,
            pg_admin_password_enc=None,
        )
        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=staff),
            ),
            patch(
                "app.services.pg_staff_access.reseller_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.load_web_admin",
                return_value={"username": "owner"},
            ),
        ):
            msg = await conflict_message_for_new_grant(AsyncMock(), "pg_x")
        self.assertIsNotNone(msg)
        self.assertIn("از قبل", msg)
        self.assertIn("staff1", msg)

    async def test_grant_ok_when_none(self):
        from app.services.pg_staff_access import conflict_message_for_new_grant

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.reseller_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.load_web_admin",
                return_value={"username": "owner"},
            ),
        ):
            msg = await conflict_message_for_new_grant(AsyncMock(), "fresh_admin")
        self.assertIsNone(msg)

    async def test_reseller_link_blocked_by_staff(self):
        from app.services.pg_staff_access import conflict_message_for_reseller_link

        staff = SimpleNamespace(id=3, web_username="s1")
        with (
            patch(
                "app.services.pg_staff_access.reseller_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=staff),
            ),
        ):
            msg = await conflict_message_for_reseller_link(AsyncMock(), "pg_y")
        self.assertIsNotNone(msg)
        self.assertIn("حذف", msg)

    async def test_reseller_link_allows_same_profile(self):
        from app.services.pg_staff_access import conflict_message_for_reseller_link

        same = SimpleNamespace(id=9, web_username="me", user_id=1)
        with (
            patch(
                "app.services.pg_staff_access.reseller_by_pg_username",
                new=AsyncMock(return_value=same),
            ),
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
        ):
            msg = await conflict_message_for_reseller_link(
                AsyncMock(), "pg_z", exclude_profile_id=9
            )
        self.assertIsNone(msg)

    async def test_grant_web_access_refuses_duplicate(self):
        from app.services.pg_staff_access import grant_web_access

        with patch(
            "app.services.pg_staff_access.conflict_message_for_new_grant",
            new=AsyncMock(return_value="قبلاً دسترسی دارد"),
        ):
            row, err = await grant_web_access(
                AsyncMock(),
                pg_username="newuser",
                web_username="newuser",
                password="AaBb12!secret",
            )
        self.assertIsNone(row)
        self.assertEqual(err, "قبلاً دسترسی دارد")


class UiTemplateGuards(unittest.TestCase):
    def test_admins_template_dual_grants(self):
        from pathlib import Path

        src = Path("app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn("src == 'reseller'", src)
        self.assertIn("دسترسی جداگانه ساخته نمی‌شود", src)
        self.assertIn("web-access/staff", src)
        self.assertIn("web-access/reseller", src)
        self.assertIn("اعطای ادمین فرعی", src)
        self.assertIn("اعطای نماینده", src)
        self.assertIn('name="plan_id"', src)
        self.assertNotIn("فعال‌سازی فروشگاه", src)
        self.assertNotIn('action="/pg/admins/{{ uname }}/web-access"', src)


if __name__ == "__main__":
    unittest.main()
