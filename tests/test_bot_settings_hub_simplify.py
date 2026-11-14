"""Bot settings hub simplification — IA + security invariants."""

from __future__ import annotations

import unittest
from types import SimpleNamespace


class BotSettingsHubIATests(unittest.TestCase):
    def test_admin_hub_order_and_titles(self):
        from app.bot.handlers.admin_settings import HUB_ORDER, SECTIONS
        from app.bot.keyboards import _admin_settings_submenu_entries

        self.assertEqual(
            HUB_ORDER,
            ["shop", "menu", "labels", "pay", "access", "limits", "buy", "support", "guides", "notify"],
        )
        self.assertNotIn("service", HUB_ORDER)
        self.assertIn("service", SECTIONS)  # deep plans callbacks still resolve
        self.assertIn("access", SECTIONS)
        self.assertEqual(SECTIONS["shop"]["title"], "نام و متن‌ها")
        self.assertEqual(SECTIONS["menu"]["title"], "ظاهر منو")
        self.assertEqual(SECTIONS["access"]["title"], "تحویل سرویس")

        labels = [lab for _, lab in _admin_settings_submenu_entries()]
        self.assertEqual(
            labels,
            [SECTIONS[sec]["title"] for sec in HUB_ORDER] + ["🌐 وب‌پنل"],
        )
        self.assertNotIn("سرویس و دسترسی", labels)
        self.assertNotIn("فروشگاه و متون", labels)

    def test_reseller_hub_aligned_with_acl_surface(self):
        from app.bot.handlers.reseller_settings import HUB_ORDER, SECTIONS
        from app.bot.keyboards import _reseller_settings_submenu_entries

        self.assertEqual(
            HUB_ORDER,
            [
                "shop",
                "menu",
                "labels",
                "pay",
                "access",
                "limits",
                "buy",
                "support",
                "guides",
                "notify",
                "bot",
            ],
        )
        self.assertEqual(SECTIONS["notify"]["title"], "اعلان‌ها")
        self.assertEqual(SECTIONS["bot"]["title"], "ربات")
        labels = [lab for _, lab in _reseller_settings_submenu_entries()]
        self.assertEqual(
            labels,
            [
                "نام و متن‌ها",
                "ظاهر منو",
                "متن دکمه‌ها",
                "پرداخت",
                "تحویل سرویس",
                "ورود و عضویت",
                "قوانین خرید",
                "پشتیبان‌ها",
                "آموزش اتصال",
                "اعلان‌ها",
                "ربات",
                "🌐 وب‌پنل",
            ],
        )

    def test_access_owns_qr_and_force_not_service(self):
        from app.bot.handlers.admin_settings import SECTIONS, _owner_screen_for_key

        access_keys = {
            f[0]
            for sub in SECTIONS["access"]["subs"]
            if isinstance(sub[2], list)
            for f in sub[2]
        }
        self.assertIn("qr_enabled", access_keys)
        self.assertNotIn("force_join_enabled", access_keys)
        service_subs = {s[0] for s in SECTIONS["service"]["subs"]}
        self.assertNotIn("qr", service_subs)
        self.assertNotIn("force", service_subs)
        # Forced channel membership lives with the other entry gates in «limits».
        self.assertEqual(_owner_screen_for_key("force_join_enabled"), ("limits", "force"))
        self.assertEqual(_owner_screen_for_key("show_sub_link_in_text"), ("access", "qr"))

    def test_shop_catalog_button_groups(self):
        from app.bot.handlers.admin_settings import SECTIONS as admin_s
        from app.bot.handlers.reseller_settings import SECTIONS as res_s
        from app.services.settings_button_labels import PLATFORM_ONLY_BTN_KEYS

        for sections in (admin_s, res_s):
            sub_ids = {s[0] for s in sections["shop"]["subs"]} | {s[0] for s in sections["labels"]["subs"]}
            self.assertIn("identity", sub_ids)
            self.assertIn("btn_main", sub_ids)
            self.assertNotIn("help_texts", sub_ids)
            self.assertNotIn("sys_texts", sub_ids)
            self.assertNotIn("btn_labels", sub_ids)

        admin_btn_keys = {
            f[0]
            for sub in admin_s["labels"]["subs"]
            if isinstance(sub[2], list)
            for f in sub[2]
            if str(f[0]).startswith("btn_")
        }
        self.assertIn("btn_reseller_apply", admin_btn_keys)
        self.assertNotIn("btn_miniapp", admin_btn_keys)
        self.assertIn("btn_wholesale", admin_btn_keys)

        res_btn_keys = {
            f[0]
            for sub in res_s["labels"]["subs"]
            if isinstance(sub[2], list)
            for f in sub[2]
            if str(f[0]).startswith("btn_")
        }
        self.assertTrue(PLATFORM_ONLY_BTN_KEYS.isdisjoint(res_btn_keys))
        self.assertIn("btn_loyalty", res_btn_keys)
        self.assertIn("btn_wholesale", res_btn_keys)

    def test_reply_map_reseller_new_labels(self):
        from app.bot.keyboards import reply_action_map, reseller_settings_reply_keyboard

        ui = {
            "menu_layout": "compact",
            "btn_back": "⬅️ بازگشت",
            "btn_menu_home": "🏠 منوی اصلی",
        }
        profile = SimpleNamespace(
            is_active=True,
            web_permissions="dashboard,plans,orders,payments,tickets,stats,shop_settings",
        )
        mapping = reply_action_map(
            "reseller",
            ui=ui,
            include_submenus=True,
            is_reseller_bot=True,
            profile=profile,
        )
        self.assertEqual(mapping["نام و متن‌ها"], "res_st_shop")
        # A shop keyboard sent before the rename still opens the same section.
        self.assertEqual(mapping["فروشگاه"], "res_st_shop")
        self.assertEqual(mapping["ربات"], "res_st_bot")
        self.assertEqual(mapping["اعلان‌ها"], "res_st_notify")
        self.assertEqual(mapping["🌐 وب‌پنل"], "res_st_panel")
        self.assertNotIn("فروشگاه و متون", mapping)
        flat = [b.text for row in reseller_settings_reply_keyboard(ui).keyboard for b in row]
        self.assertIn("نام و متن‌ها", flat)
        self.assertIn("🌐 وب‌پنل", flat)

    def test_user_cannot_see_settings_hub_labels(self):
        from app.bot.keyboards import reply_action_map

        ui = {"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت", "menu_order": "shop"}
        mapping = reply_action_map("user", ui=ui, include_submenus=True, is_reseller_bot=False)
        self.assertNotIn("فروشگاه", mapping)
        self.assertNotIn("نام و متن‌ها", mapping)
        self.assertNotIn("🌐 وب‌پنل", mapping)
        self.assertNotIn("اعلان‌ها", mapping)

    def test_admin_settings_blocked_on_reseller_bot_map(self):
        from app.bot.keyboards import reply_action_map

        ui = {"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت"}
        mapping = reply_action_map(
            "admin", ui=ui, include_submenus=True, is_reseller_bot=True
        )
        self.assertNotIn("فروشگاه", mapping)
        self.assertNotIn("adm_st_shop", mapping.values())
        self.assertNotIn("adm_st_panel", mapping.values())

    def test_colors_catalog_matches_settings_hub_actions(self):
        from app.bot.handlers.admin_settings import HUB_ORDER
        from app.bot.handlers.reseller_settings import HUB_ORDER as RES_HUB
        from app.bot.keyboards import (
            REPLY_ACTION_ADM_ST_PANEL,
            REPLY_ACTION_RES_ST_PANEL,
            _admin_settings_submenu_entries,
            _reseller_settings_submenu_entries,
        )
        from app.services.button_styles import BUTTON_STYLE_CATALOG, STYLE_ALIASES

        ids = {item["id"] for item in BUTTON_STYLE_CATALOG}
        for sec in HUB_ORDER:
            self.assertIn(f"adm_st_{sec}", ids, sec)
        self.assertIn("adm_st_panel", ids)
        self.assertEqual(STYLE_ALIASES.get("adm_st_service"), "adm_st_access")
        self.assertNotIn("adm_st_service", ids)

        for sec in RES_HUB:
            self.assertIn(f"res_st_{sec}", ids, sec)
        self.assertIn("res_st_panel", ids)

        admin_actions = {a for a, _ in _admin_settings_submenu_entries()}
        self.assertEqual(admin_actions & ids, admin_actions)
        self.assertIn(REPLY_ACTION_ADM_ST_PANEL, admin_actions)

        res_actions = {a for a, _ in _reseller_settings_submenu_entries()}
        self.assertEqual(res_actions & ids, res_actions)
        self.assertIn(REPLY_ACTION_RES_ST_PANEL, res_actions)


if __name__ == "__main__":
    unittest.main()
