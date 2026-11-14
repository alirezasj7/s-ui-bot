"""v4.1.2 — concise reseller delivery message; remove /rsetup one-time links."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.resellers import format_credentials_message

ROOT = Path(__file__).resolve().parents[1]


class CredentialsMessageV412Tests(unittest.TestCase):
    def test_plan_above_type_and_no_login_url(self):
        text = format_credentials_message(
            {
                "plan_name": "طلایی PAYG",
                "billing_mode": "payg",
                "unified_credentials": True,
                "panel_username": "shop_x",
                "panel_password": "Aa1!bbbbbbbb",
                "panel_url": "https://panel.example",
                "pg_panel_url": "https://pg.example/x",
                "share_pg_panel_url": True,
            }
        )
        self.assertIn("طلایی PAYG", text)
        self.assertIn("PAYG", text)
        plan_idx = text.find("طلایی PAYG")
        type_idx = text.find("PAYG")
        self.assertLess(plan_idx, type_idx)
        self.assertIn("<b>ورود یکپارچه</b>", text)
        self.assertIn("<b>آدرس وب‌پنل</b>", text)
        self.assertNotIn("/login", text)
        self.assertNotIn("rsetup", text)
        self.assertNotIn("ربات اختصاصی (اختیاری)", text)
        self.assertIn("داشبورد وب‌پنل", text)
        self.assertNotIn("کمیسیون", text)

    def test_no_setup_url_even_if_passed(self):
        text = format_credentials_message(
            {
                "unified_credentials": True,
                "panel_username": "u",
                "panel_password": "p",
                "panel_url": "https://p.example",
                "setup_url": "https://p.example/rsetup/deadbeef",
            }
        )
        self.assertNotIn("rsetup", text)
        self.assertNotIn("یک‌بارمصرف", text)
        self.assertNotIn("کمیسیون", text)


class RsetupRemovedV412Tests(unittest.TestCase):
    def test_no_rsetup_surface(self):
        self.assertFalse((ROOT / "app/api/reseller_setup.py").exists())
        self.assertFalse((ROOT / "app/web/templates/reseller_setup.html").exists())
        edit = (ROOT / "app/web/templates/reseller_edit.html").read_text(encoding="utf-8")
        self.assertNotIn("reissue_setup", edit)
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        self.assertNotIn("new_setup_token", src)
        self.assertNotIn("setup_url", src)
        provision = src.split("async def provision_reseller", 1)[1].split(
            "def format_credentials_message", 1
        )[0]
        self.assertNotIn("rsetup", provision)


if __name__ == "__main__":
    unittest.main()
