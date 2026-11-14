"""A non-admin cannot change platform settings through any settings handler."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import _RequireBotOwnerPrincipal
from app.bot.handlers import admin_settings

READ_ONLY_HANDLERS = {"settings_noop", "settings_hub"}
MUTATORS = ("set_setting", "upsert_support_contact", "delete_support_contact")


def _handlers():
    router = admin_settings.router
    seen = {}
    for observer in (router.callback_query, router.message):
        for handler in observer.handlers:
            seen[handler.callback.__name__] = handler.callback
    return seen


async def _state() -> FSMContext:
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=5, user_id=5))
    await state.update_data(edit_key="shop_title", edit_loc=("shop", "identity"))
    return state


def _kwargs(fn, state):
    callback = MagicMock()
    callback.data = "adm:st:tog:shop_title"
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    message = MagicMock()
    message.text = "hostile value"
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    available = {
        "callback": callback,
        "message": message,
        "state": state,
        "session": MagicMock(),
        "db_user": SimpleNamespace(role="user", telegram_id=999, id=999),
        "is_reseller_bot": False,
    }
    return {k: v for k, v in available.items() if k in inspect.signature(fn).parameters}


class SettingsAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_cannot_mutate_settings_from_any_handler(self):
        handlers = _handlers()
        self.assertGreater(len(handlers), 20)
        patches = {
            name: patch.object(admin_settings, name, AsyncMock())
            for name in MUTATORS
        }
        mocks = {name: p.start() for name, p in patches.items()}
        self.addCleanup(lambda: [p.stop() for p in patches.values()])
        for name, fn in handlers.items():
            if name in READ_ONLY_HANDLERS:
                continue
            try:
                await fn(**_kwargs(fn, await _state()))
            except Exception:  # a handler rejecting odd input is fine; mutation is not
                continue
        for name, mock in mocks.items():
            mock.assert_not_awaited()

    async def test_middleware_denies_non_owner_outside_settings_flow(self):
        gate = _RequireBotOwnerPrincipal()
        handler = AsyncMock()
        event = MagicMock()
        event.data = "adm:st:tog:shop_title"
        event.answer = AsyncMock()
        data = {
            "session": MagicMock(),
            "db_user": SimpleNamespace(role="user"),
            "state": await _state(),
        }
        with patch("app.bot.auth.is_bot_owner_principal", AsyncMock(return_value=False)):
            result = await gate(handler, event, data)
        self.assertIsNone(result)
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
