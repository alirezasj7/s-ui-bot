"""Unit tests for reseller bot access and PG overview helpers."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pg_overview import _status_meta, _time_meter
from app.services.reseller_access import (
    effective_menu_role,
    is_bot_admin_id,
    normalize_telegram_ids_csv,
    parse_telegram_ids,
    resolve_reseller_owner_id,
)


class ParseIdsTests(unittest.TestCase):
    def test_parse_mixed_separators(self):
        self.assertEqual(parse_telegram_ids("1, 2;3\n4"), {1, 2, 3, 4})

    def test_parse_ignores_junk(self):
        self.assertEqual(parse_telegram_ids("1,abc,,2"), {1, 2})

    def test_parse_ignores_synthetic_ids(self):
        self.assertEqual(parse_telegram_ids("10,-99,0,-2100000000000001"), {10})

    def test_normalize_sorts(self):
        self.assertEqual(normalize_telegram_ids_csv("3,1,2"), "1,2,3")
        self.assertIsNone(normalize_telegram_ids_csv("  "))


class BotAdminIdTests(unittest.TestCase):
    def test_is_bot_admin_id(self):
        profile = SimpleNamespace(bot_admin_ids="10,20")
        self.assertTrue(is_bot_admin_id(profile, 10))
        self.assertFalse(is_bot_admin_id(profile, 99))
        self.assertFalse(is_bot_admin_id(None, 10))
        self.assertFalse(is_bot_admin_id(profile, -10))
        synth_profile = SimpleNamespace(bot_admin_ids="-99,10")
        self.assertFalse(is_bot_admin_id(synth_profile, -99))


class ResolveOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_bot_reseller_has_no_panel_actor(self):
        """Shop panel ops are dedicated-bot only — main bot never elevates."""
        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        owner = await resolve_reseller_owner_id(
            MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
        )
        self.assertIsNone(owner)

    async def test_main_bot_bot_admin_stays_user(self):
        user = SimpleNamespace(id=9, role="user", telegram_id=777)
        with patch(
            "app.services.reseller_access.get_reseller_profile",
            new=AsyncMock(return_value=SimpleNamespace(bot_admin_ids="777", is_active=True)),
        ):
            owner = await resolve_reseller_owner_id(
                MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
            )
        self.assertIsNone(owner)

    async def test_dedicated_bot_owner(self):
        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        owner = await resolve_reseller_owner_id(
            MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
        )
        self.assertEqual(owner, 5)

    async def test_dedicated_bot_admin_ids(self):
        user = SimpleNamespace(id=9, role="user", telegram_id=777)
        profile = SimpleNamespace(bot_admin_ids="777,888", is_active=True, user_id=5)
        with patch(
            "app.services.reseller_access.get_reseller_profile",
            new=AsyncMock(return_value=profile),
        ):
            owner = await resolve_reseller_owner_id(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
            )
        self.assertEqual(owner, 5)

    async def test_dedicated_bot_platform_admin_not_owner(self):
        user = SimpleNamespace(id=1, role="admin", telegram_id=1)
        with patch(
            "app.services.reseller_access.get_reseller_profile",
            new=AsyncMock(return_value=SimpleNamespace(bot_admin_ids="", is_active=True)),
        ):
            owner = await resolve_reseller_owner_id(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
            )
        self.assertIsNone(owner)

    async def test_effective_menu_role_demotes_admin_on_shop_bot(self):
        user = SimpleNamespace(id=1, role="admin", telegram_id=1)
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(None, None)),
        ):
            role = await effective_menu_role(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
            )
        self.assertEqual(role, "user")

    async def test_effective_menu_role_reseller_panel_on_shop_bot(self):
        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        profile = SimpleNamespace(is_active=True, user_id=5)
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(5, profile)),
        ):
            role = await effective_menu_role(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
            )
        self.assertEqual(role, "reseller")

    async def test_effective_menu_role_demotes_reseller_on_main_bot(self):
        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(None, None)),
        ):
            role = await effective_menu_role(
                MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
            )
        self.assertEqual(role, "user")


class PgOverviewHelpersTests(unittest.TestCase):
    def test_status_meta(self):
        self.assertEqual(_status_meta("active"), ("فعال", "active"))
        self.assertEqual(_status_meta("limited"), ("محدود", "warn"))
        self.assertEqual(_status_meta(None), (None, None))

    def test_time_meter_without_created(self):
        # Far-future expire → remain > 0, total_text falls back to expire text
        meter = _time_meter(4102444800)  # 2100-01-01
        self.assertIsNotNone(meter)
        assert meter is not None
        self.assertTrue(meter["has_limit"])
        self.assertEqual(meter["total_text"], meter["expire_text"])
        self.assertNotEqual(meter["remain_text"], "منقضی")


class ImportSmokeTests(unittest.TestCase):
    def test_import_handlers(self):
        from app.bot.handlers import reseller, reseller_plans, reseller_settings, start, services

        self.assertTrue(hasattr(reseller, "res_home"))
        self.assertTrue(hasattr(reseller_plans, "res_plan_webhint"))
        self.assertTrue(hasattr(reseller_settings, "_gate"))
        self.assertTrue(hasattr(start, "render_home"))
        self.assertTrue(hasattr(services, "svc_list"))

    def test_webhint_signature_has_session(self):
        import inspect
        from app.bot.handlers.reseller_plans import res_plan_webhint

        params = inspect.signature(res_plan_webhint).parameters
        self.assertIn("session", params)


if __name__ == "__main__":
    unittest.main()
