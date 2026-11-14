"""Per-item button colors for support contacts and payment destinations."""

from __future__ import annotations

import unittest


class ItemButtonStyleTests(unittest.TestCase):
    def test_parse_and_serialize_item_style(self):
        from app.services.button_styles import (
            parse_item_button_style_form,
            parse_item_button_style_raw,
            serialize_item_button_style,
        )

        self.assertIsNone(parse_item_button_style_raw(None))
        self.assertIsNone(parse_item_button_style_raw("inherit"))
        self.assertEqual(parse_item_button_style_raw(""), "")
        self.assertEqual(parse_item_button_style_raw("success"), "success")
        self.assertEqual(parse_item_button_style_raw("bogus"), "")
        self.assertEqual(serialize_item_button_style("inherit"), {})
        self.assertEqual(serialize_item_button_style(""), {"button_style": ""})
        self.assertEqual(serialize_item_button_style("primary"), {"button_style": "primary"})
        self.assertIsNone(parse_item_button_style_form({"button_style": "inherit"}))

    def test_resolve_payment_destination_style(self):
        from app.services.button_styles import resolve_payment_destination_style, setting_key

        ui = {setting_key("pay_card"): "success"}
        self.assertEqual(
            resolve_payment_destination_style(ui, {}, "card"),
            "success",
        )
        self.assertEqual(
            resolve_payment_destination_style(ui, {"button_style": "danger"}, "card"),
            "danger",
        )
        self.assertIsNone(
            resolve_payment_destination_style(ui, {"button_style": ""}, "card"),
        )

    def test_resolve_support_contact_style(self):
        from app.services.button_styles import resolve_support_contact_style, setting_key

        ui = {setting_key("support"): "primary"}
        self.assertEqual(resolve_support_contact_style(ui, {}), "primary")
        self.assertEqual(
            resolve_support_contact_style(ui, {"button_style": "success"}),
            "success",
        )

    def test_support_contacts_persist_style(self):
        from pathlib import Path

        src = Path("app/services/support_contacts.py").read_text(encoding="utf-8")
        self.assertIn("serialize_item_button_style", src)
        self.assertIn("button_style is not _STYLE_UNSET", src)

    def test_payment_cards_persist_style(self):
        from app.services.payment_destinations import dump_payment_cards, parse_payment_cards

        raw = dump_payment_cards(
            [
                {
                    "id": "c1",
                    "number": "6037991234567890",
                    "holder": "Ali",
                    "enabled": True,
                    "sort": 0,
                    "button_style": "success",
                }
            ]
        )
        cards = parse_payment_cards(raw)
        self.assertEqual(cards[0]["button_style"], "success")

    def test_support_keyboard_applies_style(self):
        from pathlib import Path

        src = Path("app/bot/keyboards.py").read_text(encoding="utf-8")
        self.assertIn("resolve_support_contact_style", src)
        self.assertIn('kwargs["style"]', src)

    def test_colors_page_template_subtabs(self):
        from pathlib import Path

        html = Path("app/web/templates/_settings_colors.html").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("data-colors-subtabs", html)
        self.assertIn("section-tabs", html)
        self.assertIn("colors_page_sections", html)
        self.assertNotIn("btn-color-chip", html)
        self.assertIn("colors-groups-stack", html)
        self.assertIn("colors-group-summary-inner", html)
        self.assertIn("colors-group-summary-inner", css)
        self.assertIn("display: block !important", css)
        self.assertIn("colors-chevron-ico", html)
        self.assertIn("colors-dynamic-list", html)
        settings = Path("app/web/templates/settings.html").read_text(encoding="utf-8")
        self.assertNotIn("'colors','daily_report'", settings)
        self.assertNotIn("colors','daily_report'", settings)

    def test_dynamic_color_rows_tab_mapping(self):
        from app.services.button_styles import build_dynamic_color_summary

        rows = build_dynamic_color_summary(
            {},
            support_contacts=[{"title": "S", "button_style": "primary"}],
            payment_cards=[{"number": "6037991234567890", "button_style": "success"}],
        )
        kinds = {r["kind"]: r["tab"] for r in rows}
        self.assertEqual(kinds["support"], "user")
        self.assertEqual(kinds["pay_card"], "payment")

    def test_simplified_catalog_labels(self):
        from app.services.button_styles import CATALOG_BY_ID

        self.assertIn("پلن ثابت", CATALOG_BY_ID["shop_kind_fixed"]["label"])
        self.assertIn("PAYG", CATALOG_BY_ID["plan_res_payg"]["label"])
        self.assertNotIn("زیرمنو هم همین رنگ", CATALOG_BY_ID["shop_kind_fixed"]["label"])

    def test_colors_page_grouped_sections(self):
        from app.services.button_styles import colors_page_grouped_sections

        sections = colors_page_grouped_sections()
        tab_ids = [s[0] for s in sections]
        self.assertEqual(tab_ids, ["user", "payment", "admin", "reseller"])


if __name__ == "__main__":
    unittest.main()
