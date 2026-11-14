"""Tests for unified PG+web credentials and reply-keyboard main menu (3.5.5)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.keyboards import (
    REPLY_ACTION_ADMIN,
    REPLY_ACTION_HOME,
    REPLY_ACTION_SHOP,
    _menu_layout,
    admin_reply_keyboard,
    main_reply_keyboard,
    reply_action_map,
)
from app.services.resellers import format_credentials_message


class ReplyKeyboardMenuTests(unittest.TestCase):
    def test_default_layout_is_compact(self):
        self.assertEqual(_menu_layout({}), "compact")
        self.assertEqual(_menu_layout({"menu_layout": "classic"}), "classic")

    def test_user_reply_keyboard_two_columns_when_compact(self):
        ui = {
            "menu_layout": "compact",
            "menu_order": "shop,wallet,support,loyalty",
            "btn_shop": "خرید",
            "btn_wallet": "کیف پول",
            "btn_support": "پشتیبانی",
            "btn_loyalty": "باشگاه",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        kb = main_reply_keyboard("user", has_services=False, ui=ui)
        rows = kb.keyboard
        # 4 items → 2 compact rows + restart footer (home label is submenu-only)
        self.assertEqual(len(rows[0]), 2)
        self.assertEqual(len(rows[1]), 2)
        self.assertEqual(len(rows[-1]), 1)
        self.assertEqual(rows[-1][0].text, "🔄 شروع مجدد")
        self.assertFalse(kb.is_persistent)

    def test_guide_faq_stripped_from_reply_keyboard(self):
        ui = {
            "menu_layout": "compact",
            "menu_order": "shop,guide,faq,wallet",
            "btn_shop": "خرید",
            "btn_wallet": "کیف",
            "btn_guide": "راهنما",
            "btn_faq": "سوالات",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        kb = main_reply_keyboard("user", has_services=False, ui=ui)
        flat = [b.text for row in kb.keyboard for b in row]
        self.assertIn("خرید", flat)
        self.assertIn("کیف", flat)
        self.assertNotIn("راهنما", flat)
        self.assertNotIn("سوالات", flat)

    def test_cancel_reply_is_cancel_only(self):
        from app.bot.keyboards import cancel_reply

        kb = cancel_reply({})
        flat = [b.text for row in kb.keyboard for b in row]
        self.assertEqual(flat, ["انصراف"])
        self.assertFalse(kb.is_persistent)

    def test_reply_action_map_resolves_labels(self):
        ui = {
            "menu_order": "shop,wallet",
            "btn_shop": "🟢 خرید",
            "btn_wallet": "کیف",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        mapping = reply_action_map("user", has_services=False, ui=ui)
        self.assertEqual(mapping["🟢 خرید"], REPLY_ACTION_SHOP)
        self.assertEqual(mapping["🏠 منوی اصلی"], REPLY_ACTION_HOME)

    def test_admin_reply_keyboard_includes_hub_groups(self):
        from app.bot.keyboards import REPLY_ACTION_ADM_HUB_OPS, REPLY_ACTION_ADMIN_ORDERS

        ui = {
            "menu_layout": "compact",
            "btn_admin": "🛠 پنل ادمین",
            "btn_adm_orders": "🛒 سفارش‌ها",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
        }
        mapping = reply_action_map("admin", ui=ui)
        self.assertEqual(mapping["🛒 سفارش‌ها"], REPLY_ACTION_ADMIN_ORDERS)
        self.assertEqual(mapping["🗓 عملیات روزانه"], REPLY_ACTION_ADM_HUB_OPS)
        main_flat = [
            b.text for row in main_reply_keyboard("admin", ui=ui).keyboard for b in row
        ]
        self.assertIn("🛠 پنل ادمین", main_flat)
        self.assertNotIn("🗓 عملیات روزانه", main_flat)
        flat = [b.text for row in admin_reply_keyboard(ui).keyboard for b in row]
        self.assertIn("🗓 عملیات روزانه", flat)
        self.assertIn("👤 افراد", flat)
        self.assertNotIn("🛒 سفارش‌ها", flat)
        self.assertNotIn("📊 داشبورد", flat)


class UnifiedCredentialsMessageTests(unittest.TestCase):
    def test_unified_credentials_block(self):
        text = format_credentials_message(
            {
                "plan_name": "نقره‌ای",
                "billing_mode": "fixed",
                "unified_credentials": True,
                "panel_username": "shop_abc",
                "panel_password": "Secret1!",
                "panel_url": "https://panel.example",
                "pg_panel_url": "https://pg.example",
                "share_pg_panel_url": True,
                "web_username": "shop_abc",
                "web_password": "Secret1!",
                "pg_username": "shop_abc",
                "pg_password": "Secret1!",
            }
        )
        self.assertIn("ورود یکپارچه", text)
        self.assertIn("نقره‌ای", text)
        self.assertIn("ثابت", text)
        self.assertNotIn("کمیسیون", text)
        self.assertIn("shop_abc", text)
        self.assertIn("Secret1!", text)
        self.assertIn("https://panel.example", text)
        self.assertNotIn("/login", text)
        self.assertNotIn("rsetup", text)
        self.assertNotIn("ربات اختصاصی (اختیاری)", text)
        # Should not duplicate separate web/pg credential sections
        self.assertNotIn("وب‌پنل ربات (نماینده)", text)

    def test_legacy_separate_credentials_still_format(self):
        text = format_credentials_message(
            {
                "unified_credentials": False,
                "web_username": "web_x",
                "web_password": "WebPass1!",
                "pg_username": "pg_y",
                "pg_password": "PgPass1!",
                "panel_url": "https://panel.example",
                "pg_panel_url": "https://pg.example",
                "share_pg_panel_url": True,
            }
        )
        self.assertIn("پنل پاسارگارد", text)
        self.assertIn("وب‌پنل ربات", text)
        self.assertIn("web_x", text)
        self.assertIn("pg_y", text)
        self.assertNotIn("/login", text)


class ApplyResellerPasswordTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_password_updates_web_and_pg(self):
        from app.services.resellers import apply_reseller_panel_password

        profile = MagicMock()
        profile.pg_admin_username = "shop_abc"
        profile.web_username = "shop_abc"
        profile.web_password_hash = None
        profile.pg_admin_password_enc = None
        profile.pg_api_key_enc = None

        session = AsyncMock()
        mock_pg = AsyncMock()
        with (
            patch(
                "app.services.org_principals.get_principal_by_reseller_profile",
                new=AsyncMock(return_value=None),
            ),
            patch("app.services.pasarguard.get_pg", return_value=mock_pg),
            patch("app.services.pasarguard.reset_pg"),
            patch("app.services.secret_box.encrypt_secret", return_value="enc"),
            patch("app.services.web_auth.hash_password", return_value="hashed"),
            patch(
                "app.services.credential_policy.validate_password_strength",
                return_value=(True, None),
            ),
        ):
            await apply_reseller_panel_password(session, profile, "NewPass1!", sync_pg=True)

        self.assertEqual(profile.web_password_hash, "hashed")
        self.assertEqual(profile.pg_admin_password_enc, "enc")
        mock_pg.modify_admin.assert_awaited_once_with("shop_abc", {"password": "NewPass1!"})


if __name__ == "__main__":
    unittest.main()
