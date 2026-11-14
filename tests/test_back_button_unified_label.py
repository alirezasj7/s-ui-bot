"""Every back button shows the shared «بازگشت» label and keeps its callback."""

from __future__ import annotations

import unittest

from app.bot import keyboards as kb
from app.bot.handlers import admin_settings


def _texts(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


class BackButtonLabelTests(unittest.TestCase):
    def test_plan_kind_back_buttons_use_the_configured_back_label(self):
        ui = {"btn_back": "بازگشت سفارشی"}
        for audience in ("users", "resellers"):
            markup = kb.admin_plan_kind_keyboard(audience, ui)
            self.assertIn("بازگشت سفارشی", _texts(markup))
            self.assertFalse([t for t in _texts(markup) if t.startswith("⬅️ پلن")])

    def test_default_label_is_plain_back(self):
        markup = kb.admin_plan_kind_keyboard("users", None)
        backs = [t for t in _texts(markup) if "بازگشت" in t]
        self.assertTrue(backs)
        self.assertFalse([t for t in _texts(markup) if t.startswith("⬅️ مخاطب")])

    def test_settings_back_row_keeps_callback(self):
        (button,) = admin_settings._back_row("adm:st:hub")
        self.assertEqual(button.callback_data, "adm:st:hub")
        self.assertIn("بازگشت", button.text)

    def test_support_list_back_is_not_named_after_the_step(self):
        row = admin_settings._back_row("adm:st:sec:support")
        self.assertNotIn("لیست", row[0].text)


if __name__ == "__main__":
    unittest.main()
