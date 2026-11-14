"""Typing «انصراف» in a prompt goes where its inline «انصراف» goes, not to the main menu."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import nav_input
from app.bot.handlers import admin_plans, shop, support, wallet
from app.bot.nav_input import CANCEL_CODE_KEY, PROMPT_CHAT_ID, PROMPT_MSG_ID

CHAT_ID = 31


async def _waiting(code: str) -> FSMContext:
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=CHAT_ID))
    await state.set_state("Some:prompt")
    await state.update_data(**{PROMPT_MSG_ID: 700, PROMPT_CHAT_ID: CHAT_ID, CANCEL_CODE_KEY: code})
    return state


def _typed(text: str = "انصراف") -> MagicMock:
    message = MagicMock(text=text, chat=SimpleNamespace(id=CHAT_ID), message_id=701)
    message.from_user = SimpleNamespace(id=CHAT_ID, is_bot=False)
    message.delete = AsyncMock()
    message.answer = AsyncMock()
    return message


class CustomerPromptCancelTests(unittest.IsolatedAsyncioTestCase):
    async def _cancel(self, module: Any, handler: Any, code: str, fallback: str) -> tuple[AsyncMock, AsyncMock]:
        reopen = AsyncMock()
        state = await _waiting(code)
        with (
            patch.dict(nav_input.CANCEL_REGISTRY, {code: nav_input.CancelEntry(reopen=reopen)}),
            patch.object(module, "get_all_settings", AsyncMock(return_value={}), create=True),
            patch(fallback, AsyncMock()) as main_menu,
        ):
            await handler(_typed(), state=state, session=MagicMock(), db_user=MagicMock())
        self.assertIsNone(await state.get_state())
        return reopen, main_menu

    async def test_each_prompt_reopens_its_own_screen(self) -> None:
        cases = (
            (wallet, wallet.wallet_topup_amount, "w_amt", "app.bot.menu_nav.restore_main_reply"),
            (shop, shop.wholesale_qty_entered, "w_qty", "app.bot.menu_nav.restore_main_reply"),
            (support, support.support_subject, "s_subj", "app.bot.tg_utils.clear_fsm_with_reply"),
            (support, support.support_body, "s_body", "app.bot.tg_utils.clear_fsm_with_reply"),
        )
        for module, handler, code, fallback in cases:
            with self.subTest(handler=handler.__name__):
                reopen, main_menu = await self._cancel(module, handler, code, fallback)
                reopen.assert_awaited_once()
                main_menu.assert_not_awaited()

    async def test_the_home_button_still_goes_home_from_a_top_up_amount(self) -> None:
        reopen = AsyncMock()
        state = await _waiting("w_amt")
        with (
            patch.dict(nav_input.CANCEL_REGISTRY, {"w_amt": nav_input.CancelEntry(reopen=reopen)}),
            patch.object(wallet, "get_all_settings", AsyncMock(return_value={})),
            patch.object(wallet.kb, "is_home_text", return_value=True),
            patch("app.bot.menu_nav.restore_main_reply", AsyncMock()) as main_menu,
        ):
            await wallet.wallet_topup_amount(_typed("🏠 منوی اصلی"), state, MagicMock(), MagicMock())
        reopen.assert_not_awaited()
        main_menu.assert_awaited_once()


class ResellerPlanPromptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        for patcher in (
            patch("app.bot.auth.require_bot_owner", AsyncMock(return_value=True)),
            patch.object(admin_plans, "_is_admin", return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_typed_cancel_of_a_field_edit_reopens_its_plan(self) -> None:
        reopen = AsyncMock()
        state = await _waiting("adm_resplan_edit_test")
        with (
            patch.dict(nav_input.CANCEL_REGISTRY, {"adm_resplan_edit_test": nav_input.CancelEntry(reopen=reopen)}),
            patch.object(admin_plans, "_answer_plans_cancel", AsyncMock()) as plans_home,
        ):
            await admin_plans.resplan_edit_save(_typed(), state, MagicMock(), MagicMock())
        reopen.assert_awaited_once()
        plans_home.assert_not_awaited()

    async def test_back_to_the_plan_lists_stops_waiting_for_a_typed_answer(self) -> None:
        state = await _waiting("adm_resplan_edit_test")
        callback = MagicMock(data="adm:plans:aud:resellers")
        callback.answer = AsyncMock()
        with (
            patch.object(admin_plans, "send_resellers_plans_overview", AsyncMock()) as overview,
            patch.object(admin_plans.nav, "set_nav_level", AsyncMock()),
        ):
            await admin_plans.plans_aud_inline_back(callback, MagicMock(), MagicMock(), state)
        overview.assert_awaited_once()
        self.assertIsNone(await state.get_state())


if __name__ == "__main__":
    unittest.main()
