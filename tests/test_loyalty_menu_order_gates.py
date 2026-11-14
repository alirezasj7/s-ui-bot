"""Loyalty menu: feature toggles + submenu order without forced re-inject."""

from __future__ import annotations

import unittest

from app.bot.keyboards import REPLY_ACTION_LOYALTY, REPLY_ACTION_LOY_WHEEL, main_reply_keyboard
from app.bot.reply_keyboards import _loyalty_submenu_entries, loyalty_reply_keyboard
from app.services.lucky_wheel import parse_submenu_order


class SubmenuOrderParseTests(unittest.TestCase):
    def test_fill_missing_default_reinjects(self):
        order = parse_submenu_order("loy_wheel,loy_points,bogus")
        self.assertEqual(order[0], "loy_wheel")
        self.assertIn("loy_history", order)
        self.assertNotIn("bogus", order)

    def test_fill_missing_false_keeps_omissions(self):
        order = parse_submenu_order(
            "loy_points,loy_rewards", fill_missing=False
        )
        self.assertEqual(order, ["loy_points", "loy_rewards"])
        self.assertNotIn("loy_wheel", order)

    def test_empty_falls_back_to_defaults(self):
        order = parse_submenu_order("", fill_missing=False)
        self.assertIn("loy_referral", order)
        self.assertIn("loy_wheel", order)


class LoyaltyFeatureGateTests(unittest.TestCase):
    def test_main_menu_hides_loyalty_when_disabled(self):
        ui = {
            "menu_layout": "compact",
            "menu_order": "shop,loyalty,wallet",
            "loyalty_enabled": "0",
            "btn_shop": "خرید",
            "btn_loyalty": "باشگاه",
            "btn_wallet": "کیف",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        kb = main_reply_keyboard("user", ui=ui)
        labels = [b.text for row in kb.keyboard for b in row]
        self.assertIn("خرید", labels)
        self.assertNotIn("باشگاه", labels)

    def test_main_menu_shows_loyalty_when_enabled(self):
        ui = {
            "menu_layout": "compact",
            "menu_order": "shop,loyalty",
            "loyalty_enabled": "1",
            "btn_shop": "خرید",
            "btn_loyalty": "باشگاه",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        kb = main_reply_keyboard("user", ui=ui)
        labels = [b.text for row in kb.keyboard for b in row]
        self.assertIn("باشگاه", labels)

    def test_wheel_hidden_when_toggle_off(self):
        ui = {
            "loyalty_submenu_order": "loy_referral,loy_wheel,loy_history",
            "lucky_wheel_enabled": "0",
            "btn_referral": "دعوت",
            "btn_loy_wheel": "گردونه",
            "btn_loy_history": "تاریخچه",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
        }
        entries = _loyalty_submenu_entries(ui)
        keys = [k for k, _ in entries]
        self.assertIn("loy_referral", keys)
        self.assertNotIn(REPLY_ACTION_LOY_WHEEL, keys)
        labels = [b.text for row in loyalty_reply_keyboard(ui).keyboard for b in row]
        self.assertNotIn("گردونه", labels)
        self.assertIn("دعوت", labels)

    def test_wheel_shown_when_toggle_on(self):
        ui = {
            "loyalty_submenu_order": "loy_wheel,loy_history",
            "lucky_wheel_enabled": "1",
            "btn_loy_wheel": "گردونه",
            "btn_loy_history": "تاریخچه",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
        }
        keys = [k for k, _ in _loyalty_submenu_entries(ui)]
        self.assertEqual(keys[0], REPLY_ACTION_LOY_WHEEL)

    def test_omitted_submenu_item_stays_hidden(self):
        ui = {
            "loyalty_submenu_order": "loy_points,loy_history",
            "lucky_wheel_enabled": "1",
            "btn_loy_points": "امتیاز",
            "btn_loy_history": "تاریخچه",
            "btn_loy_rewards": "جوایز",
            "btn_menu_home": "🏠 منوی اصلی",
            "btn_back": "⬅️ بازگشت",
        }
        keys = [k for k, _ in _loyalty_submenu_entries(ui)]
        self.assertEqual(keys, ["loy_points", "loy_history"])
        self.assertNotIn("loy_rewards", keys)


class RewardsSortOrderPanelTests(unittest.TestCase):
    def test_rewards_panel_has_sort_order_fields(self):
        from pathlib import Path

        html = Path("app/web/templates/_loyalty_rewards_panel.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="sort_order"', html)
        self.assertGreaterEqual(html.count('name="sort_order"'), 2)

    def test_create_and_save_accept_sort_order(self):
        from pathlib import Path

        src = Path("app/api/loyalty_pages.py").read_text(encoding="utf-8")
        create = src.split("async def loyalty_reward_create", 1)[1].split(
            "async def loyalty_reward_save", 1
        )[0]
        save = src.split("async def loyalty_reward_save", 1)[1].split(
            "async def loyalty_reward_archive", 1
        )[0]
        self.assertIn("sort_order: int = Form", create)
        self.assertIn("sort_order: int = Form", save)
        self.assertIn("reward.sort_order = int(sort_order)", save)


if __name__ == "__main__":
    unittest.main()
