"""Settings Back hub + silent cancel heal (+ miniapp Open-only guards)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class MiniappOpenOnlyPathTests(unittest.TestCase):
    def test_no_deprecated_miniapp_reply_or_inline_helpers(self):
        import app.bot.keyboards as kb
        import app.bot.nav_inline as nav

        self.assertFalse(hasattr(nav, "miniapp_reply_button"))
        self.assertFalse(hasattr(kb, "miniapp_inline_keyboard"))
        self.assertFalse(hasattr(kb, "miniapp_reseller_keyboard"))

    def test_legacy_reply_miniapp_hints_open(self):
        src = (ROOT / "app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        self.assertIn("if action == kb.REPLY_ACTION_MINIAPP:", src)
        self.assertIn("مینی‌اپ را از دکمهٔ Open کنار کادر پیام باز کنید.", src)
        self.assertNotIn("miniapp_inline_keyboard", src)


class SettingsHubBackTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_hub_uses_section_keyboard(self):
        from app.bot.handlers.admin_settings import _render_hub

        callback = AsyncMock()
        callback.message = AsyncMock()
        session = AsyncMock()
        ui = {"menu_order": "shop"}

        with (
            patch(
                "app.bot.handlers.admin_settings.get_all_settings",
                AsyncMock(return_value=ui),
            ),
            patch(
                "app.bot.handlers.admin_settings.safe_edit_text",
                new_callable=AsyncMock,
            ) as edit,
            patch(
                "app.bot.nav_inline.admin_settings_hub_keyboard",
                return_value=MagicMock(name="HUB_KB"),
            ) as hub_kb,
        ):
            await _render_hub(callback, session)

        hub_kb.assert_called_once_with(ui)
        edit.assert_awaited()
        kwargs = edit.await_args.kwargs
        self.assertIs(kwargs.get("reply_markup"), hub_kb.return_value)
        self.assertIn("دکمه‌های زیر", edit.await_args.args[1])
        self.assertNotIn("کیبورد پایین", edit.await_args.args[1])


class WholesaleBackKeyboardTests(unittest.TestCase):
    def test_wholesale_plan_list_back_goes_to_shop_hub(self):
        from types import SimpleNamespace

        from app.bot.keyboards import wholesale_plans_keyboard

        plan = SimpleNamespace(id=1, name="نامحدود", price=199000, is_trial=False)
        kb = wholesale_plans_keyboard([plan], {"btn_back": "⬅️ بازگشت"})
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("shop:list", data)
        self.assertNotEqual(data[-1], "shop:kind:wholesale")
        self.assertEqual(kb.inline_keyboard[-1][0].callback_data, "shop:list")


class SilentCancelHealTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_staff_nav_skips_لغو_شد_heal_when_reopening(self):
        from app.bot.nav_chrome import answer_staff_nav

        message = AsyncMock()
        session = AsyncMock()
        db_user = MagicMock()
        state = AsyncMock()
        reopen = AsyncMock()

        with (
            patch(
                "app.bot.nav_chrome.get_all_settings",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.bot.nav_chrome.heal_main_reply",
                new_callable=AsyncMock,
            ) as heal,
            patch(
                "app.bot.nav_inline.is_bot_panel_message",
                return_value=True,
            ),
        ):
            await answer_staff_nav(
                message,
                session,
                db_user,
                text="لغو شد.",
                classic=None,
                state=state,
                reopen_panel=reopen,
                clear_state=True,
                is_reseller_bot=False,
                reseller_owner_id=None,
            )

        heal.assert_not_awaited()
        reopen.assert_awaited()


if __name__ == "__main__":
    unittest.main()
