"""Phase C1 — PasarGuard read isolation tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pg_read import (
    PG_READ_ISOLATION_MSG,
    PgReadDenied,
    effective_pg_menu_keys,
    staff_has_own_pg_read,
    staff_pg_read_client,
    trust_pg_list_scope,
)
from app.services.plans_catalog import filter_groups_for_staff, filter_templates_for_staff


class StaffPgReadClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_uses_owner_client(self):
        fake = object()
        owner = {
            "role": "admin",
            "web_owner": True,
            "pg_is_owner": True,
            "org_principal_id": 1,
            "org_depth": 0,
            "org_parent_id": None,
            "org_status": "active",
        }
        with patch("app.services.pg_read.get_pg", return_value=fake):
            client = await staff_pg_read_client(None, owner)
        self.assertIs(client, fake)
        with self.assertRaises(PgReadDenied):
            await staff_pg_read_client(None, {"role": "admin"})

    async def test_reseller_uses_shop_client(self):
        fake = object()
        session = MagicMock()
        with patch(
            "app.services.pg_read.get_pg_for_reseller",
            new=AsyncMock(return_value=fake),
        ) as m:
            client = await staff_pg_read_client(
                session, {"role": "reseller", "bot_user_id": 9}
            )
        self.assertIs(client, fake)
        m.assert_awaited_once_with(session, 9)

    async def test_pg_staff_denied_without_credentials(self):
        from app.services.pasarguard import PasarGuardError

        with patch(
            "app.services.pg_read.get_pg_for_staff",
            new=AsyncMock(side_effect=PasarGuardError("رمز ذخیره نشده")),
        ):
            with self.assertRaises(PgReadDenied) as ctx:
                await staff_pg_read_client(
                    MagicMock(),
                    {"role": "pg_staff", "pg_admin_username": "staff1"},
                )
        self.assertIn("رمز", ctx.exception.message)

    async def test_pg_staff_with_credentials_uses_staff_client(self):
        fake = object()
        with patch(
            "app.services.pg_read.get_pg_for_staff",
            new=AsyncMock(return_value=fake),
        ) as m:
            client = await staff_pg_read_client(
                MagicMock(),
                {
                    "role": "pg_staff",
                    "pg_admin_username": "staff1",
                    "pg_staff_id": 4,
                    "pg_credentials_ready": True,
                },
            )
        self.assertIs(client, fake)
        m.assert_awaited_once()

    async def test_reseller_without_shop_denied(self):
        with self.assertRaises(PgReadDenied):
            await staff_pg_read_client(
                MagicMock(),
                {"role": "reseller", "bot_user_id": None},
            )


class MenuDataAlignmentTests(unittest.TestCase):
    def test_reseller_keeps_mapped_keys(self):
        staff = {
            "role": "reseller",
            "bot_user_id": 1,
            "pg_permissions": ["pg_overview", "pg_users", "pg_hosts"],
        }
        self.assertTrue(staff_has_own_pg_read(staff))
        self.assertEqual(
            effective_pg_menu_keys(staff),
            ["pg_overview", "pg_users", "pg_hosts"],
        )

    def test_pg_staff_menu_overview_only_without_credentials(self):
        staff = {
            "role": "pg_staff",
            "pg_credentials_ready": False,
            "pg_permissions": ["pg_overview", "pg_users", "pg_hosts", "pg_nodes"],
        }
        self.assertFalse(staff_has_own_pg_read(staff))
        self.assertEqual(effective_pg_menu_keys(staff), ["pg_overview"])

    def test_pg_staff_menu_full_with_credentials(self):
        staff = {
            "role": "pg_staff",
            "pg_credentials_ready": True,
            "pg_permissions": ["pg_overview", "pg_users", "pg_hosts", "pg_nodes"],
        }
        self.assertTrue(staff_has_own_pg_read(staff))
        self.assertEqual(
            effective_pg_menu_keys(staff),
            ["pg_overview", "pg_users", "pg_hosts", "pg_nodes"],
        )


class FilterFailClosedTests(unittest.TestCase):
    def test_none_allow_list_fail_closed_without_trust(self):
        staff = {"role": "pg_staff", "pg_access": {}}
        items = [{"id": 1}, {"id": 2}]
        self.assertEqual(
            filter_templates_for_staff(items, staff, trust_client_scope=False),
            [],
        )
        self.assertEqual(
            filter_groups_for_staff(items, staff, trust_client_scope=False),
            [],
        )

    def test_none_allow_list_pass_when_trusted_reseller(self):
        staff = {
            "role": "reseller",
            "bot_user_id": 3,
            "pg_access": {},
        }
        self.assertTrue(trust_pg_list_scope(staff))
        items = [{"id": 1}]
        self.assertEqual(
            filter_templates_for_staff(items, staff, trust_client_scope=True),
            items,
        )

    def test_explicit_allow_list(self):
        staff = {
            "role": "reseller",
            "bot_user_id": 3,
            "pg_access": {"allowed_template_ids": [2]},
        }
        items = [{"id": 1}, {"id": 2}]
        self.assertEqual(
            filter_templates_for_staff(items, staff),
            [{"id": 2}],
        )


class SourceGuardReadPathsTests(unittest.TestCase):
    def test_list_gets_use_staff_pg_read_client(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        for marker in (
            'async def pg_users(',
            'async def pg_templates(',
            'async def pg_groups(',
            'async def pg_hosts(',
            'async def pg_nodes(',
            'async def pg_inbounds(',
        ):
            idx = src.find(marker)
            self.assertGreater(idx, 0, marker)
            chunk = src[idx : idx + 900]
            self.assertIn("staff_pg_read_client", chunk, marker)
            # Must not hardcode owner client for the list fetch
            self.assertNotIn("pg = get_pg()", chunk, marker)

    def test_writes_still_use_staff_pg(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("async def _staff_pg(", src)
        self.assertIn("await _staff_pg(session, staff)", src)

    def test_overview_no_unscoped_user_fallback(self):
        src = Path("app/services/pg_overview.py").read_text(encoding="utf-8")
        self.assertIn("never fall back to an unscoped", src)
        # The dangerous pattern: get_users without admin= after empty filtered list
        self.assertNotIn("get_users(limit=stats", src)


class OwnedUserStatsIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_unscoped_fallback(self):
        from app.services.pg_overview import _owned_user_stats

        pg = MagicMock()
        pg.get_users = AsyncMock(side_effect=Exception("no admin filter"))
        stats = await _owned_user_stats(pg, "alice", fallback_total=5)
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["online"], 0)
        # Only one attempt — with admin=
        pg.get_users.assert_awaited()
        kwargs = pg.get_users.await_args.kwargs
        self.assertEqual(kwargs.get("admin"), "alice")


if __name__ == "__main__":
    unittest.main()
