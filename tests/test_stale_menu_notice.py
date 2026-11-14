"""Unrecognised plain text (usually a stale keyboard button) gets one throttled menu refresh."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User

from app.bot.handlers import stale_menu
from app.services.stale_menu import STALE_NOTICE_WINDOW_SECONDS, should_send_stale_notice


class ThrottleTests(unittest.TestCase):
    def test_first_notice_is_allowed(self) -> None:
        self.assertTrue(should_send_stale_notice(None))

    def test_repeat_within_window_is_blocked(self) -> None:
        now = datetime.now(timezone.utc)
        last = (now - timedelta(seconds=5)).timestamp()
        self.assertFalse(should_send_stale_notice(last, now=now))

    def test_notice_allowed_after_window(self) -> None:
        now = datetime.now(timezone.utc)
        last = (now - timedelta(seconds=STALE_NOTICE_WINDOW_SECONDS + 1)).timestamp()
        self.assertTrue(should_send_stale_notice(last, now=now))

    def test_malformed_or_future_values_do_not_silence_notice(self) -> None:
        now = datetime.now(timezone.utc)
        for bad in ("x", True, {}, (now + timedelta(days=1)).timestamp()):
            self.assertTrue(should_send_stale_notice(bad, now=now), bad)


class _Flow(StatesGroup):
    typing = State()


class HandlerRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        # The module-level router can only be attached once; detach between tests.
        stale_menu.router._parent_router = None
        self.dp.include_router(stale_menu.router)

        async def inject(handler, event, data):
            data["session"] = MagicMock()
            data["db_user"] = MagicMock()
            return await handler(event, data)

        self.dp.update.outer_middleware(inject)
        self.bot = Bot("123456:TEST")
        self.heal = AsyncMock()
        patcher = patch.object(stale_menu, "heal_main_reply", new=self.heal)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def _send(self, text: str, *, chat_type: str = "private") -> None:
        user = User(id=7, is_bot=False, first_name="u")
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=7, type=chat_type),
            from_user=user,
            text=text,
        ).as_(self.bot)
        await self.dp.feed_update(self.bot, Update(update_id=1, message=message))

    async def test_unknown_text_refreshes_menu_once_then_throttles(self) -> None:
        await self._send("🔴 دکمه قدیمی")
        await self._send("🔴 دکمه قدیمی")
        self.heal.assert_awaited_once()
        self.assertEqual(self.heal.await_args.kwargs["text"], stale_menu.STALE_NOTICE_TEXT)

    async def test_commands_are_ignored(self) -> None:
        await self._send("/unknown")
        self.heal.assert_not_awaited()

    async def test_group_chats_are_ignored(self) -> None:
        await self._send("hello", chat_type="supergroup")
        self.heal.assert_not_awaited()

    async def test_text_during_a_flow_is_not_intercepted(self) -> None:
        key = StorageKey(bot_id=self.bot.id, chat_id=7, user_id=7)
        await self.storage.set_state(key, _Flow.typing.state)
        await self._send("12345")
        self.heal.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
