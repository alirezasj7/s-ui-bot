"""Subordinate digests + staff risk-color tags — security and formatting guards."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.color_tags import (
    COLOR_TAGS,
    DEFAULT_COLOR_TAG,
    FILTER_NONE,
    VALID_COLOR_KEYS,
    apply_color_tag,
    bot_tag_button_label,
    color_tag_meta,
    effective_color_tag,
    normalize_color_filter,
    normalize_color_tag,
)
from app.services.subordinate_report import (
    SubordinateShop,
    SubordinateStats,
    format_subordinate_report,
    list_direct_subordinate_shops,
)
from app.services.users_ops import users_list_href


class ColorTagTests(unittest.TestCase):
    def test_palette_is_exactly_four_risk_levels(self):
        self.assertEqual(len(VALID_COLOR_KEYS), 4)
        self.assertEqual(
            {t.key for t in COLOR_TAGS},
            {"green", "yellow", "orange", "red"},
        )
        self.assertEqual(DEFAULT_COLOR_TAG, "green")
        titles = {t.key: t.title_fa for t in COLOR_TAGS}
        self.assertEqual(titles["green"], "مطمئن")
        self.assertEqual(titles["yellow"], "مشکوک")
        self.assertEqual(titles["orange"], "ریسک")
        self.assertEqual(titles["red"], "ریسک بالا")

    def test_normalize_rejects_freeform_defaults_green(self):
        self.assertEqual(normalize_color_tag("#ff0000"), "green")
        self.assertEqual(normalize_color_tag("javascript:alert(1)"), "green")
        self.assertEqual(normalize_color_tag("RED"), "red")
        self.assertEqual(normalize_color_tag("none"), "green")
        self.assertEqual(normalize_color_tag(None), "green")
        self.assertEqual(normalize_color_tag(""), "green")

    def test_legacy_aliases(self):
        self.assertEqual(normalize_color_tag("amber"), "yellow")
        self.assertEqual(normalize_color_tag("blue"), "green")
        self.assertEqual(normalize_color_filter("_none"), "green")
        self.assertEqual(normalize_color_filter(FILTER_NONE), "green")
        self.assertIsNone(normalize_color_filter("all"))
        self.assertIsNone(normalize_color_filter("nope"))

    def test_apply_color_tag_never_clears(self):
        class U:
            color_tag = None

        u = U()
        self.assertEqual(apply_color_tag(u, "green"), "green")
        self.assertEqual(u.color_tag, "green")
        self.assertEqual(apply_color_tag(u, ""), "green")
        self.assertEqual(u.color_tag, "green")
        self.assertEqual(apply_color_tag(u, "orange"), "orange")

    def test_meta_effective_and_href(self):
        meta = color_tag_meta("orange")
        self.assertIsNotNone(meta)
        self.assertTrue(meta.hex.startswith("#"))
        self.assertEqual(meta.title_fa, "ریسک")
        self.assertEqual(color_tag_meta(None).key, "green")
        self.assertEqual(effective_color_tag(type("U", (), {"color_tag": None})()), "green")
        self.assertIn("مطمئن", bot_tag_button_label("green"))
        href = users_list_href(filter_key="alerts", color="red", q="ali")
        self.assertIn("filter=alerts", href)
        self.assertIn("color=red", href)
        self.assertIn("q=ali", href)


class MiniAppKeyboardGuardTests(unittest.TestCase):
    def _settings(self, public_base_url: str):
        from app.config import Settings

        return Settings(_env_file=None, public_base_url=public_base_url)

    def test_miniapp_requires_https(self):
        with patch("app.services.ssl_certs.https_is_active", return_value=False):
            plain = self._settings("http://bot.example.com")
            self.assertFalse(plain.miniapp_enabled)
            self.assertEqual(plain.miniapp_url, "")
            self.assertEqual(plain.miniapp_deep_url("ops"), "")

            secure = self._settings("https://bot.example.com/")
            self.assertTrue(secure.miniapp_enabled)
            self.assertEqual(secure.miniapp_url, "https://bot.example.com/miniapp/")
            self.assertEqual(
                secure.miniapp_deep_url("#ops"), "https://bot.example.com/miniapp/#ops"
            )


class BotRiskTagKeyboardTests(unittest.TestCase):
    def test_user_and_reseller_pickers_expose_four_levels(self):
        from app.bot import keyboards as kb

        user_kb = kb.admin_user_risk_tag_keyboard(9, current="yellow")
        reseller_kb = kb.admin_reseller_risk_tag_keyboard(9, current="yellow")
        for markup, prefix in (
            (user_kb, "adm:users:tagset:9:"),
            (reseller_kb, "adm:resellers:tagset:9:"),
        ):
            keys = [
                (b.callback_data or "").rsplit(":", 1)[-1]
                for row in markup.inline_keyboard
                for b in row
                if (b.callback_data or "").startswith(prefix)
            ]
            self.assertEqual(set(keys), {"green", "yellow", "orange", "red"})
        actions = kb.admin_reseller_actions(9, color_tag="red")
        self.assertTrue(
            any(
                (b.callback_data or "") == "adm:resellers:tag:9"
                for row in actions.inline_keyboard
                for b in row
            )
        )


class SubordinateReportFormatTests(unittest.TestCase):
    def test_format_escapes_names(self):
        shop = SubordinateShop(
            principal_id=1,
            reseller_profile_id=2,
            reseller_user_id=3,
            display_name='<script>x</script>',
            is_active=True,
        )
        rows = [
            SubordinateStats(
                shop=shop,
                users_new=1,
                users_total=10,
                orders_new=2,
                orders_delivered=1,
                revenue_today=5000,
                services_total=3,
                traffic_text="1/10 GB",
            )
        ]
        text = format_subordinate_report(rows)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertIn("کاربران جدید: 1", text)
        self.assertIn("حجم:", text)

    def test_empty_children_message(self):
        text = format_subordinate_report([])
        self.assertIn("زیرمجموعه‌ای", text)


class SubordinateScopeUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_l2_parent_returns_empty(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.org_principals import DEPTH_TWO, STATUS_ACTIVE

        parent = MagicMock()
        parent.id = 9
        parent.depth = DEPTH_TWO
        parent.status = STATUS_ACTIVE
        parent.parent_id = 1
        session = AsyncMock()
        out = await list_direct_subordinate_shops(session, parent=parent)
        self.assertEqual(out, [])
        session.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
