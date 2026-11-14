"""The bot's menu-order editors show a Persian label for every menu item, never the raw key."""

from __future__ import annotations

import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import admin_settings, reseller_settings
from app.bot.keyboards import DEFAULT_MENU_ORDER
from app.services.connection_status_texts import CONNECTION_STATUS_MENU_KEY

SHOP_HIDDEN_KEYS = {"reseller_apply", "miniapp"}


class MenuOrderLabelTests(unittest.IsolatedAsyncioTestCase):
    def test_every_platform_menu_item_has_a_persian_label(self) -> None:
        for key in DEFAULT_MENU_ORDER:
            with self.subTest(key=key):
                label = admin_settings.MENU_ORDER_LABELS.get(key, "")
                self.assertTrue(label)
                self.assertIsNone(re.search(r"[A-Za-z]", label), label)

    def test_every_shop_menu_item_has_a_persian_label(self) -> None:
        for key in DEFAULT_MENU_ORDER:
            if key in SHOP_HIDDEN_KEYS:
                continue
            with self.subTest(key=key):
                label = reseller_settings.MENU_ORDER_LABELS.get(key, "")
                self.assertTrue(label)
                self.assertIsNone(re.search(r"[A-Za-z]", label), label)

    async def test_platform_editor_shows_the_connection_status_item_by_its_persian_name(self) -> None:
        edit = AsyncMock()
        callback = SimpleNamespace(message=SimpleNamespace(edit_text=edit))
        order = f"shop,services,{CONNECTION_STATUS_MENU_KEY},wallet"
        with patch.object(admin_settings, "get_all_settings", AsyncMock(return_value={"menu_order": order})):
            await admin_settings._render_menu_order(callback, object(), "adm:st:hub")
        texts = [button.text for row in edit.call_args.kwargs["reply_markup"].inline_keyboard for button in row]
        self.assertIn("3. وضعیت اتصال", texts)
        self.assertNotIn(CONNECTION_STATUS_MENU_KEY, " ".join(texts))


if __name__ == "__main__":
    unittest.main()
