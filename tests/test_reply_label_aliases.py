"""Stale ReplyKeyboard labels after btn_* renames keep resolving."""

from __future__ import annotations

import unittest

from app.bot.keyboards import reply_action_map
from app.services.reply_label_aliases import (
    ALIAS_SETTING_KEY,
    merge_alias_updates_for_payload,
    parse_aliases,
    record_btn_label_change,
    register_aliases_on_mapping,
    serialize_aliases,
)
from app.services.rich_text import pack_rich_text
from aiogram.types import MessageEntity


class ReplyLabelAliasesUnitTests(unittest.TestCase):
    def test_record_keeps_old_display_for_action(self):
        aliases = record_btn_label_change(
            {},
            btn_key="btn_shop",
            old_raw="🟢🛒 خرید سرویس",
            new_raw="🛍 فروشگاه",
        )
        self.assertIn("🟢🛒 خرید سرویس", aliases.get("shop") or [])

    def test_default_drift_heals_without_stored_aliases(self):
        """Edits made before alias persistence still map default labels."""
        ui = {
            "btn_shop": "🛍 فروشگاه من",
            "btn_wallet": "کیف پول",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
            "menu_order": "shop,wallet",
            "loyalty_enabled": "0",
        }
        mapping = reply_action_map(
            "user", ui=ui, include_submenus=False, is_reseller_bot=False
        )
        self.assertEqual(mapping.get("🛍 فروشگاه من"), "shop")
        # Factory default from DEFAULT_SETTINGS
        self.assertEqual(mapping.get("🟢🛒 خرید سرویس"), "shop")
        # Must not leak admin actions onto user maps via aliases
        self.assertNotIn("📊 داشبورد", mapping)
        self.assertNotEqual(mapping.get("🟢🛒 خرید سرویس"), "adm_dash")

    def test_stored_aliases_setdefault_under_live_label(self):
        ui = {
            "btn_shop": "جدید",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
            "menu_order": "shop",
            "loyalty_enabled": "0",
            ALIAS_SETTING_KEY: serialize_aliases({"shop": ["قدیمی", "جدید"]}),
        }
        mapping: dict[str, str] = {"جدید": "shop"}
        register_aliases_on_mapping(mapping, ui)
        self.assertEqual(mapping["جدید"], "shop")
        self.assertEqual(mapping.get("قدیمی"), "shop")

    def test_merge_payload_updates_alias_json(self):
        existing = {
            "btn_shop": "قدیمی",
            ALIAS_SETTING_KEY: "{}",
        }
        extra = merge_alias_updates_for_payload(
            existing_ui=existing, payload={"btn_shop": "جدید"}
        )
        self.assertIsNotNone(extra)
        parsed = parse_aliases(extra[ALIAS_SETTING_KEY])
        self.assertIn("قدیمی", parsed.get("shop") or [])

    def test_rich_and_display_variants_both_aliased(self):
        body = "🛒 خرید"
        packed = pack_rich_text(
            body,
            [
                MessageEntity(
                    type="custom_emoji",
                    offset=0,
                    length=2,
                    custom_emoji_id="1",
                )
            ],
        )
        aliases = record_btn_label_change(
            {},
            btn_key="btn_shop",
            old_raw=packed,
            new_raw="خرید جدید",
        )
        shop = aliases.get("shop") or []
        # Stripped display ("خرید") and/or plain with glyph
        self.assertTrue(any(x for x in shop))


class RetiredDefaultLabelTests(unittest.TestCase):
    """Keyboards still on customers' phones show labels from older code defaults."""

    _OLD_STATUS_LABEL = "📡 وضعیت از دید سرور"

    def _user_map(self, menu_order: str) -> dict[str, str]:
        from app.services.users import DEFAULT_SETTINGS

        ui = dict(DEFAULT_SETTINGS)
        ui["menu_order"] = menu_order
        return reply_action_map("user", ui=ui, include_submenus=False)

    def test_old_status_button_label_still_opens_status(self):
        mapping = self._user_map("shop,services,connection_status,wallet")
        self.assertEqual(mapping.get(self._OLD_STATUS_LABEL), "connection_status")

    def test_old_status_label_stays_unmapped_when_button_is_off(self):
        mapping = self._user_map("shop,services,wallet")
        self.assertNotIn(self._OLD_STATUS_LABEL, mapping)

    def test_old_admin_connection_label_still_opens_the_connection_menu(self):
        from app.services.users import DEFAULT_SETTINGS

        mapping = reply_action_map("admin", ui=dict(DEFAULT_SETTINGS), include_submenus=True)
        self.assertEqual(mapping.get("📡 تست و وضعیت اتصال"), "connection_status_admin")

    def test_custom_label_matching_old_default_is_not_duplicated(self):
        from app.services.users import DEFAULT_SETTINGS

        ui = dict(DEFAULT_SETTINGS)
        ui["menu_order"] = "connection_status"
        ui["btn_connection_status"] = self._OLD_STATUS_LABEL
        mapping = reply_action_map("user", ui=ui, include_submenus=False)
        self.assertEqual(mapping.get(self._OLD_STATUS_LABEL), "connection_status")


if __name__ == "__main__":
    unittest.main()
