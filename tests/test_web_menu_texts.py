"""Web panel «تیتر و توضیح منوها»: owner and shop scope, validation, premium emoji kept, reset to defaults."""

from __future__ import annotations

from aiogram.types import MessageEntity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import ResellerSetting, Setting
from app.services.rich_text import pack_rich_text
from app.services.screen_titles import caption_setting_key, title_setting_key
from app.services.users import DEFAULT_SETTINGS, clear_settings_cache
from tests.test_update_owner_only import OWNER_SESSION, SHOP_SESSION, RoutesHarness

OPS_TITLE = title_setting_key("a.ops")
OPS_CAPTION = caption_setting_key("a.ops")
WALLET_TITLE = title_setting_key("c.wallet")
PREMIUM = [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="5368324170671202286")]


class MenuTextsTabTests(RoutesHarness):
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

    async def store(self, key: str, value: str) -> None:
        async with self.Session() as session:
            session.add(Setting(key=key, value=value))
            await session.commit()
        clear_settings_cache()

    async def test_the_owner_sees_every_menu_and_the_editor_switch(self) -> None:
        page = await self.request(OWNER_SESSION, "GET", "/settings?tab=screens")
        self.assertEqual(page.status_code, 200)
        for name in (f"s_{OPS_TITLE}", f"s_{OPS_CAPTION}", f"s_{WALLET_TITLE}", "s_screen_editor_enabled"):
            self.assertIn(name, page.text)
        self.assertIn("بازگردانی همه به پیش‌فرض", page.text)

    async def test_the_owner_saves_a_title_and_hides_a_caption(self) -> None:
        saved = await self.request(OWNER_SESSION, "POST", "/settings?tab=screens", {f"s_{OPS_TITLE}": "🚀 کارهای امروز", f"s_{OPS_CAPTION}": "-"})
        self.assertEqual(saved.status_code, 303)
        self.assertIn("saved=1", saved.headers["location"])
        self.assertEqual(await self.stored(OPS_TITLE), "🚀 کارهای امروز")
        self.assertEqual(await self.stored(OPS_CAPTION), "-")

    async def test_an_unsafe_title_is_refused_with_the_menu_name(self) -> None:
        refused = await self.request(OWNER_SESSION, "POST", "/settings?tab=screens", {f"s_{OPS_TITLE}": "<b>x</b>"})
        self.assertIn("err=", refused.headers["location"])
        self.assertIsNone(await self.stored(OPS_TITLE))

    async def test_a_premium_title_shows_as_text_and_survives_an_unchanged_save(self) -> None:
        packed = pack_rich_text("👍 کارهای امروز", PREMIUM)
        await self.store(OPS_TITLE, packed)
        page = await self.request(OWNER_SESSION, "GET", "/settings?tab=screens")
        self.assertIn('value="👍 کارهای امروز"', page.text)
        self.assertNotIn("RICH1", page.text)
        await self.request(OWNER_SESSION, "POST", "/settings?tab=screens", {f"s_{OPS_TITLE}": "👍 کارهای امروز"})
        self.assertEqual(await self.stored(OPS_TITLE), packed)

    async def test_a_premium_button_label_shows_as_text_on_the_buttons_tab(self) -> None:
        await self.store("btn_wallet", pack_rich_text("👍 کیف پول من", PREMIUM))
        page = await self.request(OWNER_SESSION, "GET", "/settings?tab=buttons")
        self.assertIn("کیف پول من", page.text)
        self.assertNotIn("RICH1", page.text)

    async def test_reset_puts_texts_back_and_keeps_the_switch(self) -> None:
        await self.request(OWNER_SESSION, "POST", "/settings?tab=screens", {
            f"s_{OPS_TITLE}": "🚀 کارهای امروز", f"s_{OPS_CAPTION}": "توضیح من", "s_screen_editor_enabled": "1",
        })
        reset = await self.request(OWNER_SESSION, "POST", "/settings?tab=screens", {"reset_defaults": "1"})
        self.assertIn("saved=1", reset.headers["location"])
        self.assertEqual(await self.stored(OPS_TITLE), DEFAULT_SETTINGS[OPS_TITLE])
        self.assertEqual(await self.stored(OPS_CAPTION), DEFAULT_SETTINGS[OPS_CAPTION])
        self.assertEqual(await self.stored("screen_editor_enabled"), "1")

    async def test_a_shop_sees_and_saves_only_its_own_menus(self) -> None:
        page = await self.request(SHOP_SESSION, "GET", "/shop-settings?tab=screens")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f"s_{WALLET_TITLE}", page.text)
        self.assertNotIn(f"s_{OPS_TITLE}", page.text)
        self.assertNotIn("s_screen_editor_enabled", page.text)
        await self.request(SHOP_SESSION, "POST", "/shop-settings?tab=screens", {
            f"s_{WALLET_TITLE}": "💰 حساب من", f"s_{OPS_TITLE}": "نفوذ", "s_screen_editor_enabled": "1",
        })
        self.assertEqual(await self.stored(WALLET_TITLE, shop=5), "💰 حساب من")
        self.assertIsNone(await self.stored(WALLET_TITLE))
        self.assertIsNone(await self.stored(OPS_TITLE, shop=5))
        self.assertIsNone(await self.stored(OPS_TITLE))
        self.assertIsNone(await self.stored("screen_editor_enabled", shop=5))
        self.assertIsNone(await self.stored("screen_editor_enabled"))
