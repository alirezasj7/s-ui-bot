"""3.6.8 — ticket notify actually delivers; no miniapp on shop bots."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Version368Tests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__
        from app.services.updates import is_same_or_newer

        self.assertTrue(is_same_or_newer(__version__, "0.1.0"))
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), __version__)
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"0.1.0"', notes)


class TicketNotifyDeliveryTests(unittest.TestCase):
    def test_ticket_notify_bypasses_acl(self):
        src = (ROOT / "app/services/notifications.py").read_text(encoding="utf-8")
        chunk = src.split("async def _shop_recipient_chat_ids")[1].split("async def ")[0]
        self.assertIn('notify_key != "notify_new_ticket"', chunk)
        self.assertIn("deliverable_telegram_id", chunk)
        self.assertIn("ids.append(tid)", chunk)

    def test_send_returns_count(self):
        src = (ROOT / "app/services/notifications.py").read_text(encoding="utf-8")
        chunk = src.split("async def _send_to_chats")[1].split("\nasync def ")[0]
        self.assertIn("-> int", chunk)
        self.assertIn("ok += 1", chunk)

    def test_notify_new_ticket_returns_int(self):
        src = (ROOT / "app/services/notifications.py").read_text(encoding="utf-8")
        chunk = src.split("async def notify_new_ticket")[1].split("async def ")[0]
        self.assertIn("-> int", chunk)
        self.assertIn("html_mod.escape", chunk)

    def test_support_notifies_before_success_ack(self):
        src = (ROOT / "app/bot/handlers/support.py").read_text(encoding="utf-8")
        chunk = src.split("async def support_body")[1].split("@router.")[0]
        # notify runs before the success restore_main_reply call
        self.assertIn("await notify_new_ticket(", chunk)
        self.assertIn("await restore_main_reply(", chunk)
        self.assertLess(
            chunk.find("await notify_new_ticket("),
            chunk.rfind("await restore_main_reply("),
        )


class DispatchDualNotifyTests(unittest.IsolatedAsyncioTestCase):
    async def _dispatch(self, *, live_token: str, shop_token: str, key: str,
                        notify_on: bool = True):
        from app.services import notifications

        live_bot = MagicMock(token=live_token)
        other_bot = MagicMock()
        other_bot.session.close = AsyncMock()
        profile = MagicMock(bot_token=shop_token)
        with (
            patch.object(notifications, "_resolve_shop_reseller_id", AsyncMock(return_value=7)),
            patch.object(notifications, "notify_enabled", AsyncMock(return_value=notify_on)),
            patch.object(notifications, "_shop_recipient_chat_ids", AsyncMock(return_value=[111])),
            patch.object(notifications, "_send_to_chats", AsyncMock(return_value=1)) as send,
            patch(
                "app.services.resellers.get_reseller_profile",
                AsyncMock(return_value=profile),
            ),
            patch(
                "app.services.reseller_bots.open_notify_bot_for_reseller",
                AsyncMock(return_value=(other_bot, True)),
            ) as open_bot,
        ):
            count = await notifications._dispatch_dual_notify(
                live_bot, AsyncMock(), key, "text"
            )
        return count, live_bot, other_bot, send, open_bot

    async def test_dispatch_prefers_live_shop_bot(self):
        count, live_bot, _other, send, open_bot = await self._dispatch(
            live_token="123:abc", shop_token="123:abc", key="notify_new_ticket"
        )

        self.assertEqual(count, 1)
        open_bot.assert_not_awaited()
        self.assertIs(send.await_args.args[0], live_bot)

    async def test_dispatch_opens_shop_bot_when_live_bot_is_another_shop(self):
        count, _live, other_bot, send, open_bot = await self._dispatch(
            live_token="123:abc", shop_token="999:zzz", key="notify_new_ticket"
        )

        self.assertEqual(count, 1)
        open_bot.assert_awaited_once()
        self.assertIs(send.await_args.args[0], other_bot)
        other_bot.session.close.assert_awaited_once()

    async def test_disabled_shop_pref_blocks_orders_but_not_ticket_dms(self):
        order_count, *_ = await self._dispatch(
            live_token="1:a", shop_token="1:a", key="notify_new_order", notify_on=False
        )
        ticket_count, *_ = await self._dispatch(
            live_token="1:a", shop_token="1:a", key="notify_new_ticket", notify_on=False
        )

        self.assertEqual(order_count, 0)
        self.assertEqual(ticket_count, 1)

class MiniappShopSuppressionTests(unittest.TestCase):
    def test_start_welcome_is_reply_kb_open_only(self):
        src = (ROOT / "app/bot/handlers/start.py").read_text(encoding="utf-8")
        chunk = src.split("async def render_home")[1].split("async def ")[0]
        # Welcome always carries ReplyKeyboard; Mini App is MenuButton Open only.
        self.assertNotIn("miniapp_inline_keyboard", chunk)
        self.assertNotIn("mini_markup", chunk)
        self.assertIn("reply_markup=reply_kb", chunk)
        self.assertNotIn("send_reply_keyboard_last", chunk)

    def test_no_inline_webapp_keyboard_helper(self):
        src = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
        self.assertNotIn("def miniapp_inline_keyboard", src)
        self.assertNotIn("WebAppInfo", src)

    def test_shop_settings_strip_miniapp(self):
        src = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
        chunk = src.split("async def get_all_settings")[1].split("\ndef on")[0]
        self.assertIn('"miniapp"', chunk)
        self.assertIn('data["show_miniapp"] = "0"', chunk)

    def test_seed_shop_safe_menu_order(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        chunk = src.split("async def seed_reseller_shop_settings")[1].split("\nasync def ")[0]
        # "referral" menu slot was later renamed to "loyalty" (points program).
        self.assertIn("shop,services,wallet,support,loyalty", chunk)
        self.assertNotIn("miniapp", chunk.split("value =")[1].split("\n")[0])

    def test_menu_button_open_preserved(self):
        src = (ROOT / "app/bot/chat_menu.py").read_text(encoding="utf-8")
        self.assertIn("MenuButtonWebApp", src)
        self.assertIn("sync_telegram_menu_button", src)


if __name__ == "__main__":
    unittest.main()
