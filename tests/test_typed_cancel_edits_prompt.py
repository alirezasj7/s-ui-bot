"""Typing «انصراف» at a text prompt reopens the previous panel in the prompt bubble."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.nav_inline import present_nav_panel
from app.bot.nav_input import (
    CANCEL_CODE_KEY,
    CANCEL_REGISTRY,
    PROMPT_CHAT_ID,
    PROMPT_MSG_ID,
    CancelEntry,
    try_legacy_cancel,
)

CHAT = 31
PROMPT = 200
CODE = "t_cancel"


async def _reopen(message, session, db_user, state, **_kw):
    await present_nav_panel(message, text="previous panel", inline=None, state=state)


def _message(message_id: int) -> MagicMock:
    message = MagicMock()
    message.message_id = message_id
    message.chat = SimpleNamespace(id=CHAT)
    message.bot.edit_message_text = AsyncMock()
    message.answer = AsyncMock(return_value=None)
    message.delete = AsyncMock()
    return message


async def _state() -> FSMContext:
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT, user_id=CHAT))
    await state.update_data(
        **{PROMPT_MSG_ID: PROMPT, PROMPT_CHAT_ID: CHAT, CANCEL_CODE_KEY: CODE}
    )
    return state


class TypedCancelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        CANCEL_REGISTRY[CODE] = CancelEntry(reopen=_reopen)
        self.addCleanup(CANCEL_REGISTRY.pop, CODE, None)

    async def test_immediate_cancel_edits_prompt_and_deletes_reply(self):
        state = await _state()
        message = _message(PROMPT + 1)
        handled = await try_legacy_cancel(message, state, MagicMock(), MagicMock())
        self.assertTrue(handled)
        message.answer.assert_not_awaited()
        edit = message.bot.edit_message_text
        self.assertEqual(edit.await_args.kwargs["message_id"], PROMPT)
        message.delete.assert_awaited_once()

    async def test_cancel_after_other_messages_sends_fresh_panel(self):
        state = await _state()
        message = _message(PROMPT + 5)
        await try_legacy_cancel(message, state, MagicMock(), MagicMock())
        message.bot.edit_message_text.assert_not_awaited()
        message.answer.assert_awaited_once()

    async def test_unknown_cancel_code_is_not_handled(self):
        state = await _state()
        await state.update_data(**{CANCEL_CODE_KEY: "missing"})
        message = _message(PROMPT + 1)
        self.assertFalse(await try_legacy_cancel(message, state, MagicMock(), MagicMock()))
        message.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
