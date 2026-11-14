"""Web panel: reset to defaults for welcome / messages / menu, and the message field order."""

from __future__ import annotations

import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.keyboards import default_menu_layout_settings
from app.db.models import ResellerSetting, Setting
from app.services.users import DEFAULT_SETTINGS, SETTING_GROUPS, clear_settings_cache
from tests.test_update_owner_only import OWNER_SESSION, SHOP_SESSION, RoutesHarness


class ResetTabsTests(RoutesHarness):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        clear_settings_cache()
        self.addCleanup(clear_settings_cache)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def request(self, session_payload: dict, method: str, path: str, data: dict | None = None):
        cookie = f"session={self.signer.dumps(session_payload)}; csrf=token"
        headers = {"cookie": cookie, "x-csrf-token": "token", "origin": "http://panel.test"}
        return await self.client.request(method, path, headers=headers, data=data)

    async def stored(self, key: str, *, shop: int | None = None) -> str | None:
        clear_settings_cache()
        async with self.Session() as session:
            if shop is None:
                return await session.scalar(select(Setting.value).where(Setting.key == key))
            return await session.scalar(
                select(ResellerSetting.value).where(ResellerSetting.reseller_user_id == shop, ResellerSetting.key == key)
            )

    async def test_welcome_reset_brings_back_the_text_and_keeps_the_shop_name(self) -> None:
        await self.request(OWNER_SESSION, "POST", "/settings?tab=welcome", {"s_shop_title": "فروشگاه من", "s_welcome_text": "سلام"})
        page = await self.request(OWNER_SESSION, "GET", "/settings?tab=welcome")
        self.assertIn("بازگردانی همه به پیش‌فرض", page.text)
        reset = await self.request(OWNER_SESSION, "POST", "/settings?tab=welcome", {"reset_defaults": "1"})
        self.assertIn("saved=1", reset.headers["location"])
        self.assertEqual(await self.stored("welcome_text"), DEFAULT_SETTINGS["welcome_text"])
        self.assertEqual(await self.stored("shop_title"), "فروشگاه من")

    async def test_messages_reset_brings_back_the_texts(self) -> None:
        await self.request(OWNER_SESSION, "POST", "/settings?tab=messages", {"s_shop_empty_text": "خالی"})
        await self.request(OWNER_SESSION, "POST", "/settings?tab=messages", {"reset_defaults": "1"})
        self.assertEqual(await self.stored("shop_empty_text"), DEFAULT_SETTINGS["shop_empty_text"])

    async def test_menu_reset_restores_the_order_and_layout(self) -> None:
        await self.request(OWNER_SESSION, "POST", "/settings?tab=menu", {"menu_order": "wallet,shop", "menu_layout": "classic"})
        self.assertEqual(await self.stored("menu_order"), "wallet,shop")
        await self.request(OWNER_SESSION, "POST", "/settings?tab=menu", {"reset_defaults": "1"})
        self.assertEqual(await self.stored("menu_order"), DEFAULT_SETTINGS["menu_order"])
        self.assertEqual(await self.stored("menu_layout"), DEFAULT_SETTINGS["menu_layout"])

    async def test_a_shop_menu_reset_never_offers_the_reseller_application(self) -> None:
        await self.request(SHOP_SESSION, "POST", "/shop-settings?tab=menu", {"reset_defaults": "1"})
        order = await self.stored("menu_order", shop=5)
        self.assertNotIn("reseller_apply", order.split(","))
        self.assertEqual(await self.stored("show_reseller_apply", shop=5), "0")
        self.assertNotEqual(await self.stored("menu_order"), order)


class MenuDefaultsTests(unittest.TestCase):
    def test_platform_and_shop_menu_defaults(self) -> None:
        self.assertIn("reseller_apply", default_menu_layout_settings(for_shop=False)["menu_order"])
        shop = default_menu_layout_settings(for_shop=True)
        self.assertNotIn("reseller_apply", shop["menu_order"])
        self.assertEqual(shop["show_reseller_apply"], "0")

    def test_connection_status_texts_come_last(self) -> None:
        keys = [field[0] for field in SETTING_GROUPS["متن پیام‌ها"]]
        first_status = next(i for i, key in enumerate(keys) if key.startswith("connection_status_"))
        self.assertTrue(all(key.startswith("connection_status_") for key in keys[first_status:]))


if __name__ == "__main__":
    unittest.main()
