"""Loyalty transactions tab shows user labels, not internal ids."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
LOYALTY = ROOT / "app/web/templates/loyalty.html"
LOYALTY_PAGES = ROOT / "app/api/loyalty_pages.py"


class BotUserPanelLabelTests(unittest.TestCase):
    def test_prefers_username_with_at(self):
        from app.services.formatting import bot_user_panel_label

        u = SimpleNamespace(
            id=7,
            username="alice",
            full_name="Alice",
            telegram_id=123456789,
        )
        self.assertEqual(bot_user_panel_label(u), "Alice (@alice)")

    def test_username_only(self):
        from app.services.formatting import bot_user_panel_label

        u = SimpleNamespace(id=7, username="bob", full_name="", telegram_id=99)
        self.assertEqual(bot_user_panel_label(u), "@bob")

    def test_telegram_id_before_internal_id(self):
        from app.services.formatting import bot_user_panel_label

        u = SimpleNamespace(id=7, username=None, full_name=None, telegram_id=555)
        self.assertEqual(bot_user_panel_label(u), "555")
        self.assertEqual(bot_user_panel_label(None, fallback_id=7), "7")


class LoyaltyTransactionsTemplateTests(unittest.TestCase):
    def test_transactions_column_uses_user_label(self):
        html = LOYALTY.read_text(encoding="utf-8")
        self.assertIn("{{ t.user_label }}", html)
        self.assertNotIn("{{ t.user_id }}", html)

    def test_api_builds_user_label_rows(self):
        src = LOYALTY_PAGES.read_text(encoding="utf-8")
        self.assertIn("bot_user_panel_label", src)
        self.assertIn('"user_label": bot_user_panel_label(user, fallback_id=tx.user_id)', src)
        self.assertIn("select(PointsTransaction, BotUser)", src)


if __name__ == "__main__":
    unittest.main()
