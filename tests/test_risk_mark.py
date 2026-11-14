"""Telegram lists and cards show the risk tag as a colored circle, only to the shop that owns it."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.color_tags import risk_mark


class RiskMarkTests(unittest.TestCase):
    def test_the_attributing_shop_sees_the_colored_circle(self) -> None:
        platform_user = SimpleNamespace(reseller_id=None, color_tag="red")
        shop_user = SimpleNamespace(reseller_id=5, color_tag="yellow")
        self.assertEqual(risk_mark(platform_user, shop_id=None), "🔴")
        self.assertEqual(risk_mark(shop_user, shop_id=5), "🟡")
        self.assertEqual(risk_mark(SimpleNamespace(reseller_id=None, color_tag=None), shop_id=None), "🟢")

    def test_no_other_viewer_sees_the_tag(self) -> None:
        self.assertEqual(risk_mark(SimpleNamespace(reseller_id=5, color_tag="red"), shop_id=None), "")
        self.assertEqual(risk_mark(SimpleNamespace(reseller_id=5, color_tag="red"), shop_id=6), "")
        self.assertEqual(risk_mark(SimpleNamespace(reseller_id=None, color_tag="red"), shop_id=5), "")


if __name__ == "__main__":
    unittest.main()
