"""Cancel goes one step back: the prompt's origin screen is reopened as if its button was tapped."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from aiogram.types import CallbackQuery, Chat, Message, User

from app.bot import nav_input, screen_replay
from app.bot.middlewares import RateLimitMiddleware
from app.bot.nav_input import CANCEL_CODE_KEY, PROMPT_CHAT_ID, PROMPT_MSG_ID, RETURN_TO_KEY

CHAT_ID = 42
PROMPT_ID = 900
PERSON = User(id=CHAT_ID, is_bot=False, first_name="ادمین")


class _RecordingSession(BaseSession):
    """Telegram is never called; every request is recorded."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:  # noqa: ASYNC109 - BaseSession signature
        self.requests.append(method)
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover - unused
        yield b""

    async def close(self) -> None:
        return None


def _bot() -> tuple[Bot, _RecordingSession]:
    session = _RecordingSession()
    return screen_replay.install_replay_guard(Bot("123456:TEST", session=session)), session


class ScreenReplayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.opened: list[tuple[str, int]] = []
        router = Router()

        @router.callback_query(F.data.startswith("adm:users:view:"))
        async def user_card(callback: CallbackQuery) -> None:
            await callback.answer()
            await callback.message.edit_text(f"card {callback.data}")
            self.opened.append((callback.data, callback.message.message_id))

        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        screen_replay.set_dispatcher(dispatcher)
        self.addCleanup(screen_replay.set_dispatcher, None)
        self.bot, self.session = _bot()

    async def test_the_origin_screen_opens_in_the_prompt_bubble(self) -> None:
        handled = await screen_replay.replay_screen(
            self.bot, user=PERSON, chat_id=CHAT_ID, data="adm:users:view:7", message_id=PROMPT_ID
        )
        self.assertTrue(handled)
        self.assertEqual(self.opened, [("adm:users:view:7", PROMPT_ID)])
        sent = [type(m) for m in self.session.requests]
        self.assertEqual(sent, [EditMessageText])  # the replayed tap's answer never reaches Telegram

    async def test_a_real_tap_is_still_answered(self) -> None:
        await self.bot(AnswerCallbackQuery(callback_query_id="12345"))
        self.assertEqual(len(self.session.requests), 1)

    async def test_an_unknown_screen_reports_unhandled(self) -> None:
        self.assertFalse(
            await screen_replay.replay_screen(self.bot, user=PERSON, chat_id=CHAT_ID, data="nope:1", message_id=PROMPT_ID)
        )
        self.assertFalse(await screen_replay.replay_screen(self.bot, user=PERSON, chat_id=CHAT_ID, data="x" * 80, message_id=1))

    async def test_the_flood_limiter_ignores_replays(self) -> None:
        callback = CallbackQuery(id="replay:abc", from_user=PERSON, chat_instance="1", data="x")
        handler = AsyncMock(return_value="ok")
        with patch("app.bot.middlewares._rate_limited", return_value=True):
            self.assertEqual(await RateLimitMiddleware()(handler, callback, {}), "ok")


class ReplayGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_replay_passes_the_same_gates_as_a_tap(self) -> None:
        router = Router()
        seen: list[str] = []

        @router.callback_query.outer_middleware()
        async def owner_only(handler, event, data):  # stands in for the owner-principal gate
            if event.from_user.id != 1:
                return None
            return await handler(event, data)

        @router.callback_query(F.data == "adm:users")
        async def users_hub(callback: CallbackQuery) -> None:
            seen.append(callback.data)

        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        screen_replay.set_dispatcher(dispatcher)
        self.addCleanup(screen_replay.set_dispatcher, None)
        bot, _session = _bot()
        await screen_replay.replay_screen(bot, user=PERSON, chat_id=CHAT_ID, data="adm:users", message_id=PROMPT_ID)
        self.assertEqual(seen, [])


CODE = "test_cancel_one_step"


async def _prompted(**extra: Any) -> FSMContext:
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=CHAT_ID))
    await state.set_state("Some:prompt")
    await state.update_data(**{PROMPT_MSG_ID: PROMPT_ID, PROMPT_CHAT_ID: CHAT_ID, CANCEL_CODE_KEY: CODE}, **extra)
    return state


def _typed() -> MagicMock:
    message = MagicMock(text="انصراف", from_user=PERSON, chat=SimpleNamespace(id=CHAT_ID), message_id=PROMPT_ID + 1)
    message.delete = AsyncMock()
    return message


class CancelEntryPointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.reopen = AsyncMock()
        patcher = patch.dict(nav_input.CANCEL_REGISTRY, {CODE: nav_input.CancelEntry(reopen=self.reopen)})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_typed_cancel_reopens_the_origin_and_removes_the_typed_word(self) -> None:
        state = await _prompted(**{RETURN_TO_KEY: "adm:users:view:7"})
        message = _typed()
        with patch.object(nav_input, "replay_screen", AsyncMock(return_value=True)) as replay:
            self.assertTrue(await nav_input.try_legacy_cancel(message, state, MagicMock(), MagicMock()))
        self.assertEqual(replay.await_args.kwargs["data"], "adm:users:view:7")
        self.assertEqual(replay.await_args.kwargs["message_id"], PROMPT_ID)
        self.assertIs(replay.await_args.kwargs["user"], PERSON)
        message.delete.assert_awaited_once()
        self.assertIsNone(await state.get_state())
        self.assertIsNone((await state.get_data()).get(RETURN_TO_KEY))

    async def test_tapped_cancel_reopens_the_origin_in_the_same_bubble(self) -> None:
        state = await _prompted(**{RETURN_TO_KEY: "adm:users:view:7"})
        prompt = Message(message_id=PROMPT_ID, date=datetime.now(timezone.utc), chat=Chat(id=CHAT_ID, type="private")).as_(
            _bot()[0]
        )
        callback = MagicMock(data=f"nv:cancel:{CODE}", from_user=PERSON, message=prompt)
        callback.answer = AsyncMock()
        with patch.object(nav_input, "replay_screen", AsyncMock(return_value=True)) as replay:
            await nav_input.nv_cancel_input(callback, MagicMock(), MagicMock(), state)
        self.assertEqual(replay.await_args.kwargs["data"], "adm:users:view:7")
        self.assertIs(replay.await_args.kwargs["message"], prompt)
        self.assertIsNone(await state.get_state())

    async def test_without_an_origin_the_cancel_code_still_decides(self) -> None:
        state = await _prompted()
        with patch.object(nav_input, "replay_screen", AsyncMock()) as replay:
            await nav_input.try_legacy_cancel(_typed(), state, MagicMock(), MagicMock())
        replay.assert_not_awaited()
        self.reopen.assert_awaited_once()

    async def test_a_form_step_keeps_the_forms_origin(self) -> None:
        state = await _prompted(**{RETURN_TO_KEY: "adm:plans:aud:users"})
        self.assertEqual(await nav_input.form_origin(state), "adm:plans:aud:users")


class PromptOriginTests(unittest.IsolatedAsyncioTestCase):
    async def _origin(self, handler, callback_data: str, **kwargs: Any) -> str | None:
        callback = MagicMock(data=callback_data)
        callback.answer = AsyncMock()
        with (
            patch("app.bot.auth.require_bot_owner", AsyncMock(return_value=True)),
            patch.object(nav_input, "ask_text", AsyncMock()) as ask,
        ):
            await handler(callback, state=AsyncMock(), db_user=MagicMock(), **kwargs)
        return ask.await_args.kwargs["return_to"]

    async def test_user_card_prompts_return_to_the_card(self) -> None:
        from app.bot.handlers import admin

        user = SimpleNamespace(id=7, full_name="کاربر", username=None, telegram_id=70, is_blocked=False, role="user")
        with (
            patch.object(admin, "_is_admin", return_value=True),
            patch.object(admin, "_platform_shop_user", AsyncMock(return_value=(user, None))),
            patch("app.services.users.is_protected_admin", return_value=False),
        ):
            for handler, data in ((admin.adm_users_message_start, "adm:users:msg:7"), (admin.adm_users_block, "adm:users:block:7")):
                with self.subTest(handler=handler.__name__):
                    self.assertEqual(await self._origin(handler, data, session=MagicMock()), "adm:users:view:7")

    async def test_backup_prompts_return_to_the_backup_screens(self) -> None:
        from app.bot.handlers import admin_backup

        with patch.object(admin_backup, "_is_admin", return_value=True), patch.object(
            admin_backup, "get_backup_path", return_value="/tmp/b1"
        ):
            self.assertEqual(await self._origin(admin_backup.backup_restore_ask, "adm:backup:restore:b1:1"), "adm:backup:item:b1")
            self.assertEqual(await self._origin(admin_backup.backup_upload_ask, "adm:backup:upload"), "adm:backup")


if __name__ == "__main__":
    unittest.main()
