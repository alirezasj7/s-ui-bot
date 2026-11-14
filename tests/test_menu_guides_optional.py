"""Connection guides belong on the user service card (not main ReplyKeyboard)."""

from __future__ import annotations

import unittest

from app.bot.keyboards import DEFAULT_MENU_ORDER, _menu_order
from app.bot.nav_inline import service_card_keyboard
from app.services.settings_button_labels import BTN_MAIN_MENU, BTN_SERVICE_ACTIONS
from app.services.users import DEFAULT_SETTINGS


class ServiceGuidesPlacementTests(unittest.TestCase):
    def test_guides_not_on_main_menu_catalog(self):
        self.assertNotIn("guides", DEFAULT_MENU_ORDER)
        active = [
            p.strip()
            for p in str(DEFAULT_SETTINGS.get("menu_order") or "").split(",")
            if p.strip()
        ]
        self.assertNotIn("guides", active)
        self.assertNotIn("guides", _menu_order({"menu_order": DEFAULT_SETTINGS["menu_order"]}))

    def test_btn_guides_in_service_button_group_not_main(self):
        main_keys = {f[0] for f in BTN_MAIN_MENU}
        svc_keys = {f[0] for f in BTN_SERVICE_ACTIONS}
        self.assertNotIn("btn_guides", main_keys)
        self.assertIn("btn_guides", svc_keys)

    def test_service_card_uses_label_and_style(self):
        ui = {
            "btn_guides": "📘 آموزش من",
            "btn_renew": "تمدید",
            "btn_svc_addon": "حجم",
            "btn_sub_link": "لینک",
            "btn_back": "بازگشت",
            "btn_style_guides": "success",
        }
        markup = service_card_keyboard(42, ui)
        guide = None
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.callback_data == "guide:svc:42":
                    guide = btn
                    break
        self.assertIsNotNone(guide)
        self.assertEqual(guide.text, "📘 آموزش من")
        self.assertEqual(getattr(guide, "style", None), "success")


if __name__ == "__main__":
    unittest.main()
