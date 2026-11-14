"""Settings «انصراف» and «بازگشت» go one step back, typed or tapped, for the owner and for shops."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import admin_settings, reseller_settings
from app.bot.nav_input import CANCEL_CODE_KEY, PROMPT_CHAT_ID, PROMPT_MSG_ID

CHAT_ID = 77
PROMPT_ID = 501
SUPPORT = {"id": "s1", "title": "پشتیبان یک", "telegram": "@help", "enabled": True}
NO_TRIAL = MagicMock(execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None)))
PROFILE = SimpleNamespace(bot_username="shopbot", user_id=5)


async def _state(**data) -> FSMContext:
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=CHAT_ID))
    await state.update_data(**{PROMPT_MSG_ID: PROMPT_ID, PROMPT_CHAT_ID: CHAT_ID}, **data)
    return state


def _typed(text: str = "انصراف") -> MagicMock:
    message = MagicMock(text=text, html_text=text, message_id=PROMPT_ID + 1)
    message.chat = SimpleNamespace(id=CHAT_ID)
    message.from_user = SimpleNamespace(is_bot=False)
    message.bot.edit_message_text = AsyncMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    return message


def _shown(message: MagicMock) -> tuple[str, list[str]]:
    kwargs = message.bot.edit_message_text.await_args.kwargs
    markup = kwargs.get("reply_markup")
    data = [b.callback_data or b.url for row in markup.inline_keyboard for b in row] if markup else []
    return kwargs["text"], data


class OwnerSettingsCancelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        for name, value in (
            ("get_all_settings", AsyncMock(return_value={})),
            ("get_support_contacts", AsyncMock(return_value=[SUPPORT])),
        ):
            patcher = patch.object(admin_settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def _typed_cancel(self, **data) -> tuple[str, list[str]]:
        message = _typed()
        await admin_settings._silent_settings_cancel(message, await _state(**data), NO_TRIAL, MagicMock())
        return _shown(message)

    async def test_a_field_cancel_returns_to_its_subsection(self) -> None:
        text, buttons = await self._typed_cancel(edit_loc=("shop", "identity"))
        self.assertIn("نام و خوش‌آمد", text)
        self.assertIn("adm:st:edit:shop_title", buttons)

    async def test_support_prompts_return_to_the_list_or_the_support(self) -> None:
        text, buttons = await self._typed_cancel(edit_loc=("support", ""))
        self.assertIn("adm:st:sup:add", buttons)
        text, buttons = await self._typed_cancel(edit_loc=("support", "s1"))
        self.assertIn("پشتیبان یک", text)
        self.assertIn("adm:st:sup:edit:s1", buttons)

    async def test_trial_prompts_return_to_the_trial_screen(self) -> None:
        _text, buttons = await self._typed_cancel(edit_loc=("service", "trial"))
        self.assertIn("adm:st:trial:name", buttons)

    async def test_without_an_origin_the_hub_is_shown(self) -> None:
        text, _buttons = await self._typed_cancel()
        self.assertEqual(text, admin_settings._settings_hub_text({}))

    async def test_tapped_and_typed_cancel_show_the_same_screen(self) -> None:
        typed_text, typed_buttons = await self._typed_cancel(edit_loc=("shop", "identity"))
        state = await _state(edit_loc=("shop", "identity"), **{CANCEL_CODE_KEY: "adm_set"})
        prompt = _typed()
        prompt.from_user = SimpleNamespace(is_bot=True)
        prompt.edit_text = AsyncMock()
        with patch("app.bot.nav_inline.safe_edit_inline", AsyncMock(return_value=True)) as edit:
            await admin_settings.reopen_settings_location(prompt, NO_TRIAL, MagicMock(), state)
        self.assertEqual(edit.await_args.args[1], typed_text)
        tapped = [b.callback_data for row in edit.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
        self.assertEqual(tapped, typed_buttons)
        self.assertIsNone(await state.get_state())


class ShopSettingsBackCancelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        for target, value in (
            ("app.services.resellers.get_reseller_panel_base_url", AsyncMock(return_value="https://panel.test")),
            ("app.bot.handlers.reseller_settings.get_all_settings", AsyncMock(return_value={})),
            ("app.bot.handlers.reseller_settings.get_setting", AsyncMock(return_value="")),
            ("app.bot.handlers.reseller_settings.get_support_contacts", AsyncMock(return_value=[SUPPORT])),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_the_settings_home_lists_every_section(self) -> None:
        _text, markup = await reseller_settings._hub_panel(MagicMock(), PROFILE)
        buttons = [b.callback_data or b.url for row in markup.inline_keyboard for b in row]
        self.assertGreater(sum(1 for b in buttons if b and b.startswith("nv:res:ra:")), 3)
        self.assertIn("https://panel.test/shop-settings", buttons)
        self.assertEqual(buttons[-1], "nv:res:grp:shop")

    async def test_a_typed_field_cancel_returns_to_its_subsection(self) -> None:
        message = _typed()
        state = await _state(edit_key="shop_title", rs_loc=("shop", "identity"))
        await reseller_settings._typed_cancel(message, state, MagicMock(), MagicMock(), PROFILE,
                                             is_reseller_bot=True, reseller_owner_id=5)
        text, buttons = _shown(message)
        self.assertIn("res:st:edit:shop_title", buttons)
        self.assertIn("res:st:sec:shop", buttons)
        message.delete.assert_awaited()

    async def test_tapped_cancel_matches_the_typed_one(self) -> None:
        typed = _typed()
        await reseller_settings._typed_cancel(typed, await _state(rs_loc=("support", "")), MagicMock(), MagicMock(),
                                             PROFILE, is_reseller_bot=True, reseller_owner_id=5)
        prompt = _typed()
        prompt.from_user = SimpleNamespace(is_bot=True)
        state = await _state(rs_loc=("support", ""))
        with (
            patch.object(reseller_settings, "_gate", AsyncMock(return_value=(PROFILE, None))),
            patch("app.bot.nav_inline.safe_edit_inline", AsyncMock(return_value=True)) as edit,
        ):
            await reseller_settings.reopen_shop_settings_location(prompt, MagicMock(), MagicMock(), state)
        self.assertEqual(edit.await_args.args[1], _shown(typed)[0])
        self.assertIn("res:st:sup:add", [b.callback_data for row in edit.await_args.kwargs["reply_markup"].inline_keyboard for b in row])

    async def test_a_save_returns_to_the_subsection_with_a_note(self) -> None:
        message = _typed("فروشگاه من")
        state = await _state(rs_loc=("shop", "identity"))
        await reseller_settings._close_input_to_location(message, state, MagicMock(), PROFILE, note="✅ ذخیره شد.")
        text, buttons = _shown(message)
        self.assertTrue(text.startswith("✅ ذخیره شد."))
        self.assertIn("res:st:edit:shop_title", buttons)

    async def test_a_person_without_shop_settings_gets_no_panel(self) -> None:
        prompt = _typed()
        state = await _state(rs_loc=("shop", "identity"))
        with patch.object(reseller_settings, "_gate", AsyncMock(return_value=(None, "دسترسی ندارید"))):
            await reseller_settings.reopen_shop_settings_location(prompt, MagicMock(), MagicMock(), state)
        prompt.answer.assert_awaited_once_with("دسترسی ندارید")
        prompt.bot.edit_message_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
