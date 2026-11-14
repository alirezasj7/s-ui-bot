"""Existing platform and shop menus gain a working customer status button once."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from connection_monitor_support import MonitorDatabaseCase

from app.bot import keyboards
from app.db.models import ResellerSetting, Setting
from app.services.users import DEFAULT_SETTINGS


def load_menu_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "status_menu_migration", Path(__file__).resolve().parents[1] / "alembic/versions/0057_connection_status_menu.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class StatusMenuMigrationTests(MonitorDatabaseCase):
    async def test_existing_menus_gain_buttons_without_changing_other_settings(self) -> None:
        async with self.Session() as session:
            session.add(Setting(key="menu_order", value="wallet,shop"))
            session.add(Setting(key="btn_connection_status", value="وضعیت دلخواه"))
            session.add_all([
                ResellerSetting(reseller_user_id=2, key="menu_order", value="shop,services,wallet"),
                ResellerSetting(reseller_user_id=3, key="menu_order", value="wallet,connection_status,shop"),
                *[ResellerSetting(reseller_user_id=2, key=f"unrelated_{number}", value="unchanged") for number in range(205)],
            ])
            await session.commit()
        migration = await asyncio.to_thread(load_menu_migration)

        def upgrade(connection: sa.Connection) -> None:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()

        async with self.engine.begin() as connection:
            await connection.run_sync(upgrade)
        async with self.Session() as session:
            platform = await session.scalar(sa.select(Setting.value).where(Setting.key == "menu_order"))
            shops = dict((await session.execute(sa.select(ResellerSetting.reseller_user_id, ResellerSetting.value)
                         .where(ResellerSetting.key == "menu_order"))).all())
            self.assertEqual(platform, "wallet,shop,connection_status")
            self.assertEqual(shops, {2: "shop,services,connection_status,wallet", 3: "wallet,connection_status,shop"})
            self.assertEqual(await session.scalar(sa.select(Setting.value).where(Setting.key == "btn_connection_status")), "وضعیت دلخواه")
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(ResellerSetting)
                             .where(ResellerSetting.value == "unchanged")), 205)
        for order in (platform, *shops.values()):
            ui = {**DEFAULT_SETTINGS, "menu_order": order}
            reply = keyboards.main_reply_keyboard("user", ui=ui)
            inline = keyboards.main_menu("user", ui=ui)
            self.assertEqual([button.text for row in reply.keyboard for button in row].count(ui["btn_connection_status"]), 1)
            self.assertEqual([button.callback_data for row in inline.inline_keyboard for button in row].count("csp:refresh"), 1)

        def downgrade(connection: sa.Connection) -> None:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                migration.downgrade()

        async with self.engine.begin() as connection:
            await connection.run_sync(downgrade)
        async with self.Session() as session:
            self.assertEqual(await session.scalar(sa.select(Setting.value).where(Setting.key == "menu_order")), platform)
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(ResellerSetting)), 207)
