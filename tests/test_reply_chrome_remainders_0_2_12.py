"""Loyalty, backup and support panels are one inline message with no reply-chrome follow-up."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InlineKeyboardMarkup


def _user_message() -> MagicMock:
    """A user-authored message: panels must answer once, not edit."""
    message = MagicMock()
    message.from_user = MagicMock(is_bot=False)
    message.bot = None
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    return message


class InlineOnlyPanelTests(unittest.IsolatedAsyncioTestCase):
    def _assert_single_inline_panel(self, message: MagicMock) -> None:
        message.answer.assert_awaited_once()
        self.assertIsInstance(
            message.answer.await_args.kwargs["reply_markup"], InlineKeyboardMarkup
        )
        message.edit_text.assert_not_awaited()

    async def test_loyalty_referral_sends_one_inline_panel(self):
        from app.bot.handlers import loyalty

        message = _user_message()
        with (
            patch.object(loyalty, "_bot_username", AsyncMock(return_value="shop_bot")),
            patch.object(
                loyalty,
                "build_referral_text",
                AsyncMock(return_value=("invite text", "https://t.me/shop_bot?start=r1", {})),
            ),
        ):
            await loyalty.open_loyalty_referral_message(
                message, AsyncMock(), MagicMock()
            )

        self._assert_single_inline_panel(message)
        self.assertEqual(message.answer.await_args.args[0], "invite text")

    async def test_loyalty_points_sends_one_inline_panel(self):
        from app.bot.handlers import loyalty

        message = _user_message()
        db_user = MagicMock(reseller_id=None)
        with (
            patch.object(loyalty, "get_all_settings", AsyncMock(return_value={})),
            patch.object(loyalty, "loyalty_enabled", AsyncMock(return_value=True)),
            patch.object(loyalty, "build_loyalty_text", AsyncMock(return_value="points")),
        ):
            await loyalty.open_loyalty_points_message(message, AsyncMock(), db_user)

        self._assert_single_inline_panel(message)
        self.assertEqual(message.answer.await_args.args[0], "points")

    async def test_loyalty_rewards_sends_one_inline_panel_with_hub_back(self):
        from app.bot.handlers import loyalty

        message = _user_message()
        session = AsyncMock()
        db_user = MagicMock(reseller_id=None, points_balance=10)
        with (
            patch.object(loyalty, "get_all_settings", AsyncMock(return_value={})),
            patch.object(loyalty, "list_active_rewards", AsyncMock(return_value=[])),
        ):
            await loyalty.open_loyalty_rewards_message(message, session, db_user)

        self._assert_single_inline_panel(message)
        markup = message.answer.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("nv:loy:home", callbacks)

    async def test_admin_backup_hub_sends_one_inline_panel_with_files(self):
        from app.bot.handlers import reply_nav

        message = _user_message()
        with (
            patch.object(reply_nav, "_deny_unless_owner", AsyncMock(return_value=True)),
            patch.object(reply_nav, "get_all_settings", AsyncMock(return_value={})),
            patch("app.services.backup.list_backups", return_value=[]),
        ):
            await reply_nav.open_admin_backup_hub(message, AsyncMock(), MagicMock())

        self._assert_single_inline_panel(message)

    async def test_support_home_edits_panel_in_place_without_chrome_message(self):
        from app.bot.handlers import support

        callback = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()
        callback.message.answer = AsyncMock()
        ui = {"support_text": "hello", "support_contacts": ""}
        with patch.object(support, "get_all_settings", AsyncMock(return_value=ui)):
            await support.support_home(callback, AsyncMock())

        callback.message.edit_text.assert_awaited_once()
        self.assertIsInstance(
            callback.message.edit_text.await_args.kwargs["reply_markup"],
            InlineKeyboardMarkup,
        )
        callback.message.answer.assert_not_awaited()


class RemainderChromeSourceGuards(unittest.TestCase):
    def test_admin_resellers_hub_is_inline_panel(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_admin_resellers_hub)
        self.assertIn("admin_resellers_hub_keyboard", src)
        self.assertIn("present_nav_panel", src)
        self.assertNotIn("miniapp_inline_keyboard", src)


if __name__ == "__main__":
    unittest.main()
