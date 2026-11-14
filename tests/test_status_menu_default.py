"""The connection status button is off by default, named «وضعیت سرورها», and hidden from the admin menu."""

from __future__ import annotations

import asyncio
import importlib.util
import re
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from connection_monitor_support import MonitorDatabaseCase

from app.bot import keyboards
from app.bot.connection_status_public_ui import MonitorPublicLabel
from app.bot.reply_keyboards import _reply_user_entries
from app.db.models import ConnectionMonitorState, ResellerSetting, Setting
from app.db.models import Role
from app.services.connection_status_texts import (
    CONNECTION_STATUS_MENU_KEY, LEGACY_MONITOR_TEXTS, MONITOR_TEXT_DEFAULTS, readable_monitor_texts,
)
from app.services.users import DEFAULT_SETTINGS
from tests.test_update_owner_only import OWNER_SESSION, RoutesHarness

NEW_LABEL = "📡 وضعیت سرورها"


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "status_menu_default_off", Path(__file__).resolve().parents[1] / "alembic/versions/0059_status_menu_default_off.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def button_texts(markup: object) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


class StatusMenuDefaultTests(MonitorDatabaseCase):
    def test_fresh_install_does_not_show_the_button_but_the_editor_can_still_add_it(self) -> None:
        self.assertNotIn(CONNECTION_STATUS_MENU_KEY, DEFAULT_SETTINGS["menu_order"].split(","))
        self.assertNotIn(CONNECTION_STATUS_MENU_KEY, keyboards.DEFAULT_ACTIVE_MENU_ORDER)
        self.assertIn(CONNECTION_STATUS_MENU_KEY, keyboards.DEFAULT_MENU_ORDER)
        ui = dict(DEFAULT_SETTINGS)
        self.assertNotIn(NEW_LABEL, button_texts(keyboards.main_reply_keyboard("user", ui=ui)))
        ui["menu_order"] = f"shop,{CONNECTION_STATUS_MENU_KEY},wallet"
        self.assertIn(NEW_LABEL, button_texts(keyboards.main_reply_keyboard("user", ui=ui)))

    def test_admin_main_keyboard_has_no_customer_status_button_but_user_preview_keeps_it(self) -> None:
        ui = {**DEFAULT_SETTINGS, "menu_order": f"shop,{CONNECTION_STATUS_MENU_KEY},wallet"}
        admin_entries = [key for key, _ in _reply_user_entries(Role.ADMIN.value, has_services=False, ui=ui)]
        user_entries = [key for key, _ in _reply_user_entries(Role.USER.value, has_services=False, ui=ui)]
        self.assertNotIn(CONNECTION_STATUS_MENU_KEY, admin_entries)
        self.assertIn(CONNECTION_STATUS_MENU_KEY, user_entries)
        preview = keyboards.main_reply_keyboard(Role.ADMIN.value, ui=ui, as_user=True)
        self.assertIn(NEW_LABEL, button_texts(preview))

    def test_old_default_label_is_refreshed_and_a_custom_label_is_kept(self) -> None:
        old = LEGACY_MONITOR_TEXTS["btn_connection_status"]
        self.assertEqual(readable_monitor_texts({"btn_connection_status": old})["btn_connection_status"],
                         MONITOR_TEXT_DEFAULTS["btn_connection_status"])
        self.assertEqual(readable_monitor_texts({"btn_connection_status": "وضعیت دلخواه"})["btn_connection_status"], "وضعیت دلخواه")
        self.assertEqual(MONITOR_TEXT_DEFAULTS["btn_connection_status"], NEW_LABEL)

    async def test_a_keyboard_still_showing_the_old_label_keeps_working(self) -> None:
        from aiogram.types import Chat, Message, User
        from datetime import datetime, timezone

        def message(text: str) -> Message:
            return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=1, type="private"),
                           from_user=User(id=1, is_bot=False, first_name="x"), text=text)

        matcher = MonitorPublicLabel()
        async with self.Session() as session:
            self.assertTrue(await matcher(message(NEW_LABEL), session))
            self.assertTrue(await matcher(message(LEGACY_MONITOR_TEXTS["btn_connection_status"]), session))
            self.assertFalse(await matcher(message("چیز دیگر"), session))

    async def _run(self, action: str) -> None:
        migration = await asyncio.to_thread(load_migration)

        def work(connection: sa.Connection) -> None:
            with Operations.context(MigrationContext.configure(connection)):
                getattr(migration, action)()
                getattr(migration, action)()

        async with self.engine.begin() as connection:
            await connection.run_sync(work)

    async def _menus(self) -> tuple[str, dict[int, str]]:
        async with self.Session() as session:
            platform = await session.scalar(sa.select(Setting.value).where(Setting.key == "menu_order"))
            shops = dict((await session.execute(sa.select(ResellerSetting.reseller_user_id, ResellerSetting.value)
                         .where(ResellerSetting.key == "menu_order"))).all())
        return platform, shops

    async def test_menus_that_never_set_the_feature_up_lose_the_button_once(self) -> None:
        async with self.Session() as session:
            session.add(Setting(key="menu_order", value="shop,services,connection_status,wallet"))
            session.add(Setting(key="btn_connection_status", value="وضعیت دلخواه"))
            session.add_all([
                ResellerSetting(reseller_user_id=2, key="menu_order", value="shop,connection_status,wallet"),
                ResellerSetting(reseller_user_id=3, key="menu_order", value="shop,wallet"),
                *[ResellerSetting(reseller_user_id=2, key=f"unrelated_{number}", value="unchanged") for number in range(205)],
            ])
            await session.commit()
        await self._run("upgrade")
        platform, shops = await self._menus()
        self.assertEqual(platform, "shop,services,wallet")
        self.assertEqual(shops, {2: "shop,wallet", 3: "shop,wallet"})
        async with self.Session() as session:
            self.assertEqual(await session.scalar(sa.select(Setting.value).where(Setting.key == "btn_connection_status")), "وضعیت دلخواه")
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(ResellerSetting)
                             .where(ResellerSetting.value == "unchanged")), 205)
        await self._run("downgrade")
        self.assertEqual(await self._menus(), (platform, shops))

    async def test_the_platform_keeps_its_button_when_a_test_user_is_already_registered(self) -> None:
        async with self.Session() as session:
            session.add(Setting(key="menu_order", value="shop,connection_status,wallet"))
            session.add(ResellerSetting(reseller_user_id=2, key="menu_order", value="shop,connection_status,wallet"))
            session.add(ConnectionMonitorState(pg_user_id=900, pg_username="monitor-only", account_revision="one",
                                               subscription_token_enc="encrypted"))
            await session.commit()
        await self._run("upgrade")
        platform, shops = await self._menus()
        self.assertEqual(platform, "shop,connection_status,wallet")
        self.assertEqual(shops, {2: "shop,wallet"})


class MenuEditorOffersTheButtonFromTheStorageTests(RoutesHarness):
    async def test_a_default_menu_lists_the_status_button_in_the_storage_not_the_active_list(self) -> None:
        response = await self.call(OWNER_SESSION, "GET", "/settings?tab=menu")
        self.assertEqual(response.status_code, 200)
        html = response.text
        active = html.split('id="active-list"', 1)[1].split('id="pool-list"', 1)[0]
        pool = html.split('id="pool-list"', 1)[1]
        self.assertNotIn(f'data-key="{CONNECTION_STATUS_MENU_KEY}"', active)
        self.assertIn(f'data-key="{CONNECTION_STATUS_MENU_KEY}"', pool)
        self.assertEqual(len(re.findall(r'data-key="shop"', active)), 1)
