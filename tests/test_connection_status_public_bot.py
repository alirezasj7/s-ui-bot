"""Customer refresh acknowledgements, safe errors and main-menu discoverability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from connection_monitor_support import MonitorDatabaseCase

from app.bot import keyboards
from app.bot.connection_status_public_ui import MonitorPublicLabel, public_cursor, public_status_text
from app.bot.connection_status_ui import monitor_text
from app.bot.handlers import connection_status as handler
from app.services.connection_status import PublicConnectionPage, PublicConnectionStatus
from app.services.connection_status_texts import MONITOR_TEXT_DEFAULTS
from app.services.connection_status_types import ConnectionStatus
from app.services.message_variables import template_variable_specs
from app.services.users import DEFAULT_SETTINGS


class PublicStatusBotTests(MonitorDatabaseCase):
    async def test_customer_can_open_saved_status_by_tapping_the_menu_label(self) -> None:
        ui = {**DEFAULT_SETTINGS, "btn_connection_status": "وضعیت هاست‌ها"}
        message = self.message().model_copy(update={"text": ui["btn_connection_status"]})
        storage = MemoryStorage()
        self.addAsyncCleanup(storage.close)
        state = FSMContext(storage, StorageKey(bot_id=1, chat_id=101, user_id=101))
        await state.set_state("previous_input")
        with patch("app.bot.connection_status_public_ui.get_all_settings", AsyncMock(return_value=ui)), \
             patch.object(handler, "get_all_settings", AsyncMock(return_value=ui)), \
             patch.object(handler, "public_connection_page", AsyncMock(return_value=PublicConnectionPage(()))) as read, \
             patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            async with self.Session() as session:
                self.assertTrue(await MonitorPublicLabel()(message, session))
                await handler.connection_status(message, session, state)
            self.assertEqual(read.await_count, 1)
            self.assertIn(ui["connection_status_empty"], answer.call_args.args[0])
            self.assertIsNone(await state.get_state())

    def message(self) -> Message:
        return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=101, type="private"),
                       from_user=User(id=101, is_bot=False, first_name="Customer"), text="وضعیت")

    async def test_refresh_acknowledges_before_reading_and_empty_state_is_safe(self) -> None:
        message = self.message()
        callback = CallbackQuery(id="callback", from_user=message.from_user, message=message, chat_instance="synthetic", data="csp:refresh")
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
            async def read(*args: object, **kwargs: object) -> PublicConnectionPage:
                self.assertEqual(answer.await_count, 1)
                return PublicConnectionPage(())
            with patch.object(handler, "public_connection_page", side_effect=read):
                with patch.object(handler, "safe_edit_text", new_callable=AsyncMock) as edit:
                    async with self.Session() as session:
                        await handler.refresh_connection_status(callback, session)
                    self.assertIn(DEFAULT_SETTINGS["connection_status_empty"], edit.call_args.args[1])
                    self.assertIn("بررسی از سرور ربات", edit.call_args.args[1])

    async def test_read_failure_does_not_echo_database_or_panel_payload(self) -> None:
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            with patch.object(handler, "public_connection_page", AsyncMock(side_effect=RuntimeError("sensitive-token-and-address"))):
                async with self.Session() as session:
                    await handler._show(self.message(), session, after_id=0, edit=False)
                text = answer.call_args.args[0]
                self.assertEqual(text, DEFAULT_SETTINGS["connection_status_error"])
                self.assertNotIn("sensitive", text)

    async def test_status_is_discoverable_on_reply_and_inline_customer_menus_once_the_admin_adds_it(self) -> None:
        ui = {**DEFAULT_SETTINGS, "menu_order": "shop,services,connection_status,wallet"}
        reply = keyboards.main_reply_keyboard("user", has_services=False, ui=ui)
        self.assertIn(ui["btn_connection_status"], [button.text for row in reply.keyboard for button in row])
        inline = keyboards.main_menu("user", has_services=False, ui=ui)
        self.assertIn("csp:refresh", [button.callback_data for row in inline.inline_keyboard for button in row])

    async def test_status_button_is_off_by_default_and_the_page_title_identifies_the_server_vantage(self) -> None:
        default_menu = keyboards.main_menu("user", has_services=False, ui=dict(DEFAULT_SETTINGS))
        self.assertNotIn("csp:refresh", [button.callback_data for row in default_menu.inline_keyboard for button in row])
        menu = keyboards.main_menu("user", has_services=False, ui={**DEFAULT_SETTINGS, "menu_order": "shop,connection_status"})
        entry = next(button for row in menu.inline_keyboard for button in row if button.callback_data == "csp:refresh")
        self.assertEqual(entry.text, "📡 وضعیت سرورها")
        text = public_status_text(PublicConnectionPage(()), dict(DEFAULT_SETTINGS), now=self.now)
        self.assertIn("از دید سرور ربات", text)

    async def test_public_scope_notice_remains_visible_with_custom_titles_and_all_result_states(self) -> None:
        ui = {**DEFAULT_SETTINGS, "connection_status_title": "<b>عنوان سفارشی</b>"}
        pages = [PublicConnectionPage(())]
        pages.extend(PublicConnectionPage((PublicConnectionStatus("مسیر", status, checked_at),)) for status, checked_at in (
            (ConnectionStatus.HEALTHY, self.now), (ConnectionStatus.DOWN, self.now),
            (ConnectionStatus.UNKNOWN, self.now - timedelta(seconds=180)),
        ))
        for page in pages:
            with self.subTest(entries=page.entries):
                text = public_status_text(page, ui, now=self.now)
                self.assertIn("فقط دسترسی از سرور ربات", text)
                self.assertIn("اتصال شما یا دسترسی از داخل ایران را تأیید نمی‌کند", text)
                self.assertIn("&lt;b&gt;عنوان سفارشی&lt;/b&gt;", text)

    async def test_refresh_callback_never_accepts_a_shop_identifier_or_unbounded_cursor(self) -> None:
        self.assertEqual(public_cursor("csp:refresh"), 0)
        self.assertEqual(public_cursor("csp:next:10"), 10)
        for raw in ("csp:next:-1", "csp:shop:2", "csp:next:1:2", "csp:next:2147483648", "csp:next:True"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                public_cursor(raw)

    async def test_static_status_copy_has_no_dynamic_variable_metadata_or_substitution(self) -> None:
        self.assertTrue(set(MONITOR_TEXT_DEFAULTS).isdisjoint(template_variable_specs()))
        ui = dict(DEFAULT_SETTINGS)
        ui["connection_status_title"] = "{token} {user_id.__class__} <b>وضعیت</b>"
        self.assertEqual(monitor_text(ui, "connection_status_title"), "{token} {user_id.__class__} &lt;b&gt;وضعیت&lt;/b&gt;")

    async def test_status_entry_respects_menu_visibility_and_custom_position(self) -> None:
        ui = {**DEFAULT_SETTINGS, "menu_order": "wallet,connection_status,shop", "show_restart_button": "0"}
        expected = [ui["btn_wallet"], ui["btn_connection_status"], ui["btn_shop"]]
        reply = keyboards.main_reply_keyboard("user", has_services=False, ui=ui)
        inline = keyboards.main_menu("user", has_services=False, ui=ui)
        self.assertEqual([button.text for row in reply.keyboard for button in row], expected)
        self.assertEqual([button.text for row in inline.inline_keyboard for button in row], expected)
        ui["menu_order"] = "wallet,shop"
        reply = keyboards.main_reply_keyboard("user", has_services=False, ui=ui)
        inline = keyboards.main_menu("user", has_services=False, ui=ui)
        self.assertNotIn(ui["btn_connection_status"], [button.text for row in reply.keyboard for button in row])
        self.assertNotIn(ui["btn_connection_status"], [button.text for row in inline.inline_keyboard for button in row])
