"""Customer club reply-keyboard + staff ACL (Telegram)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.keyboards import (
    REPLY_ACTION_ADMIN_LOYALTY,
    REPLY_ACTION_LOYALTY,
    REPLY_ACTION_LOY_REFERRAL,
    admin_loyalty_reply_keyboard,
    loyalty_reply_keyboard,
    main_reply_keyboard,
    reply_action_map,
)


class BotLoyaltyMenuTests(unittest.TestCase):
    def test_reply_keyboard_not_force_persistent(self):
        ui = {
            "menu_layout": "compact",
            "menu_order": "shop,loyalty",
            "btn_shop": "خرید",
            "btn_loyalty": "باشگاه",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
            "btn_referral": "دعوت",
        }
        for kb in (
            main_reply_keyboard("user", ui=ui),
            loyalty_reply_keyboard(ui),
            admin_loyalty_reply_keyboard(ui, include_tiers=True),
            admin_loyalty_reply_keyboard(ui, include_tiers=False),
        ):
            self.assertFalse(kb.is_persistent)

    def test_customer_loyalty_submenu_in_action_map(self):
        ui = {
            "menu_order": "shop,loyalty",
            "btn_loyalty": "باشگاه",
            "btn_referral": "دعوت دوستان",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
        }
        mapping = reply_action_map("user", ui=ui, include_submenus=True)
        self.assertEqual(mapping["باشگاه"], REPLY_ACTION_LOYALTY)
        self.assertEqual(mapping["دعوت دوستان"], REPLY_ACTION_LOY_REFERRAL)
        self.assertIn("⭐ امتیاز من", mapping)
        self.assertIn("🎁 جوایز", mapping)

    def test_admin_hub_has_loyalty(self):
        mapping = reply_action_map(
            "admin",
            ui={"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت"},
            include_submenus=True,
            is_reseller_bot=False,
        )
        self.assertEqual(mapping["⭐ باشگاه مشتریان"], REPLY_ACTION_ADMIN_LOYALTY)
        self.assertIn("📊 نمای کلی", mapping)
        self.assertIn("🏅 سطوح", mapping)

    def test_reseller_loyalty_submenu_hides_tiers(self):
        ui = {"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت"}
        kb = admin_loyalty_reply_keyboard(ui, include_tiers=False)
        flat = [b.text for row in kb.keyboard for b in row]
        self.assertNotIn("🏅 سطوح", flat)
        self.assertIn("📐 قوانین امتیاز", flat)

    def test_redeem_scope_guard_refuses_a_reward_of_another_shop(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from app.services.loyalty import redeem_reward
        from app.services.users import reset_shop_reseller_id, set_shop_reseller_id

        reward = SimpleNamespace(enabled=True, archived=False, reseller_id=9)
        session = AsyncMock()
        no_prior = MagicMock()
        no_prior.scalar_one_or_none.return_value = None
        found = MagicMock()
        found.scalar_one_or_none.return_value = reward
        session.execute = AsyncMock(side_effect=[no_prior, found])
        token = set_shop_reseller_id(5)
        try:
            with self.assertRaisesRegex(ValueError, "این جایزه فعال نیست"):
                asyncio.run(redeem_reward(session, SimpleNamespace(id=1), 1, idempotency_key="k"))
        finally:
            reset_shop_reseller_id(token)

    def test_inline_does_not_mirror_reply_main_subsets(self):
        """Reply KB owns club nav; inline only secondary actions."""
        from app.bot.handlers import loyalty as loy_h

        reply_labels = {
            b.text
            for row in loyalty_reply_keyboard(
                {"btn_referral": "👥 دعوت دوستان", "btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت"}
            ).keyboard
            for b in row
        }
        # Main subsets must be on reply keyboard
        self.assertIn("👥 دعوت دوستان", reply_labels)
        self.assertIn("⭐ امتیاز من", reply_labels)
        self.assertIn("🎁 جوایز", reply_labels)
        self.assertIn("📜 تاریخچه", reply_labels)

        ref_labels = {
            b.text
            for row in loy_h._ref_actions_keyboard(share_url="https://t.me/share").inline_keyboard
            for b in row
        }
        points_labels = {
            b.text for row in loy_h._points_extras_keyboard().inline_keyboard for b in row
        }
        # Must not duplicate reply main subsets / home
        for forbidden in (
            "👥 دعوت دوستان",
            "⭐ امتیاز من",
            "🎁 جوایز",
            "📜 تاریخچه",
            "🏠 خانه",
            "🏠 منوی اصلی",
        ):
            self.assertNotIn(forbidden, ref_labels)
            self.assertNotIn(forbidden, points_labels)
        self.assertIn("📤 اشتراک‌گذاری لینک", ref_labels)
        self.assertIn("📊 آمار دعوت", ref_labels)
        self.assertEqual(points_labels, {"🏷 تخفیف‌های من"})

        # Legacy full menus removed
        self.assertFalse(hasattr(loy_h, "_loy_keyboard"))
        self.assertFalse(hasattr(loy_h, "_ref_keyboard"))

    def test_home_opener_has_no_quick_inline_menu(self):
        from pathlib import Path

        src = Path("app/bot/handlers/loyalty.py").read_text(encoding="utf-8")
        home = src.split("async def open_loyalty_home_message", 1)[1].split(
            "async def open_loyalty_referral_message", 1
        )[0]
        self.assertNotIn("گزینه‌های سریع", home)
        self.assertNotIn("_points_extras_keyboard", home)
        self.assertNotIn("_ref_actions_keyboard", home)


class ResolveLoyaltyManageScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_platform_admin_ok(self):
        from app.bot.handlers.loyalty import resolve_loyalty_manage_scope
        from app.db.models import Role

        user = MagicMock()
        user.role = Role.ADMIN.value
        out = await resolve_loyalty_manage_scope(
            MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
        )
        self.assertEqual(out, (None, True))

    async def test_admin_on_reseller_bot_denied(self):
        from app.bot.handlers.loyalty import resolve_loyalty_manage_scope
        from app.db.models import Role

        user = MagicMock()
        user.role = Role.ADMIN.value
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(None, None)),
        ):
            out = await resolve_loyalty_manage_scope(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=9
            )
        self.assertIsNone(out)

    async def test_reseller_with_loyalty_perm(self):
        from app.bot.handlers.loyalty import resolve_loyalty_manage_scope

        user = MagicMock()
        profile = MagicMock()
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(42, profile)),
        ), patch(
            "app.services.resellers.has_bot_perm",
            return_value=True,
        ):
            out = await resolve_loyalty_manage_scope(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=42
            )
        self.assertEqual(out, (42, False))

    async def test_reseller_without_loyalty_perm_denied(self):
        from app.bot.handlers.loyalty import resolve_loyalty_manage_scope

        user = MagicMock()
        profile = MagicMock()
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(42, profile)),
        ), patch(
            "app.services.resellers.has_bot_perm",
            return_value=False,
        ):
            out = await resolve_loyalty_manage_scope(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=42
            )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
