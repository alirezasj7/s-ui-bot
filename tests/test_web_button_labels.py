"""Web panel «متن دکمه‌ها»: every button label the bot can edit, scoped for shops."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import ResellerSetting, Setting
from app.services.settings_button_labels import PLATFORM_ONLY_BTN_KEYS, appearance_button_subs, shop_button_subs
from app.services.users import BUTTON_LABEL_GROUPS_MORE, clear_settings_cache
from tests.test_update_owner_only import OWNER_SESSION, SHOP_SESSION, RoutesHarness


def _bot_label_keys(*, include_platform: bool) -> set[str]:
    subs = [*shop_button_subs(include_platform=include_platform)]
    if include_platform:
        subs.extend(appearance_button_subs())
    return {field[0] for _sub_id, _title, fields in subs for field in fields}


class WebButtonLabelTests(RoutesHarness):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        clear_settings_cache()
        self.addCleanup(clear_settings_cache)

    async def request(self, session_payload: dict, method: str, path: str, data: dict | None = None):
        cookie = f"session={self.signer.dumps(session_payload)}; csrf=token"
        headers = {"cookie": cookie, "x-csrf-token": "token", "origin": "http://panel.test"}
        return await self.client.request(method, path, headers=headers, data=data)

    async def stored(self, key: str, *, shop: int | None = None) -> str | None:
        clear_settings_cache()
        async with async_sessionmaker(self.engine, expire_on_commit=False)() as session:
            if shop is None:
                return await session.scalar(select(Setting.value).where(Setting.key == key))
            return await session.scalar(
                select(ResellerSetting.value).where(ResellerSetting.reseller_user_id == shop, ResellerSetting.key == key)
            )

    async def test_the_owner_edits_every_label_the_bot_can_edit(self) -> None:
        page = await self.request(OWNER_SESSION, "GET", "/settings?tab=buttons")
        self.assertEqual(page.status_code, 200)
        for key in _bot_label_keys(include_platform=True):
            with self.subTest(key=key):
                self.assertIn(f'name="s_{key}"', page.text)
        self.assertNotIn('name="s_btn_miniapp"', page.text)
        saved = await self.request(OWNER_SESSION, "POST", "/settings?tab=buttons", {"s_btn_adm_plans_add": "➕ پلن تازه"})
        self.assertIn("saved=1", saved.headers["location"])
        self.assertEqual(await self.stored("btn_adm_plans_add"), "➕ پلن تازه")

    async def test_a_shop_sees_and_saves_only_its_own_labels(self) -> None:
        page = await self.request(SHOP_SESSION, "GET", "/shop-settings?tab=buttons")
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="s_btn_res_plans"', page.text)
        for key in PLATFORM_ONLY_BTN_KEYS:
            self.assertNotIn(f'name="s_{key}"', page.text, key)
        for title in BUTTON_LABEL_GROUPS_MORE:
            if title.startswith("دکمه‌های ادمین"):
                self.assertNotIn(f"<h2>{title}</h2>", page.text)
        await self.request(SHOP_SESSION, "POST", "/shop-settings?tab=buttons", {
            "s_btn_res_plans": "💎 پلن‌های من", "s_btn_adm_plans_add": "نفوذ",
        })
        self.assertEqual(await self.stored("btn_res_plans", shop=5), "💎 پلن‌های من")
        self.assertIsNone(await self.stored("btn_adm_plans_add", shop=5))
        self.assertIsNone(await self.stored("btn_adm_plans_add"))
