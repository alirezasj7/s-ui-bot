"""Bot settings with one subject per section: button labels by audience, old buttons still work."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.bot.handlers import admin_settings, reseller_settings
from app.bot.handlers.settings_labels import labels_audience_panel, labels_home_panel
from app.services.retired_text_defaults import refresh_retired_defaults
from app.services.users import DEFAULT_SETTINGS


def _callback() -> SimpleNamespace:
    return SimpleNamespace(message=AsyncMock(), answer=AsyncMock(), data="x")


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _shown(callback: SimpleNamespace) -> tuple[str, list[str]]:
    call = callback.message.edit_text.await_args
    return call.args[0], _callbacks(call.kwargs["reply_markup"])


class LabelAudienceTests(unittest.TestCase):
    def test_the_owner_picks_customer_admin_or_reseller_menus(self) -> None:
        _text, markup = labels_home_panel("adm", admin_settings.SECTIONS["labels"]["subs"])
        self.assertEqual(_callbacks(markup), ["adm:st:lab:user", "adm:st:lab:admin", "adm:st:lab:reseller", "adm:st:hub"])

    def test_a_shop_never_sees_admin_panel_labels(self) -> None:
        subs = reseller_settings.SECTIONS["labels"]["subs"]
        _text, markup = labels_home_panel("res", subs)
        self.assertEqual(_callbacks(markup), ["res:st:lab:user", "res:st:lab:reseller", "res:st:hub"])
        self.assertIsNone(labels_audience_panel("res", "admin", subs))

    def test_every_screen_backs_up_one_step(self) -> None:
        subs = admin_settings.SECTIONS["labels"]["subs"]
        _text, markup = labels_audience_panel("adm", "admin", subs)
        self.assertEqual(_callbacks(markup)[-1], "adm:st:sec:labels")
        self.assertTrue(all(c.startswith("adm:st:sub:labels:btn_adm") for c in _callbacks(markup)[:-1]))


class SectionLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_label_group_backs_up_to_its_audience(self) -> None:
        callback = _callback()
        with patch.object(admin_settings, "get_all_settings", AsyncMock(return_value={})):
            await admin_settings._render_sub(callback, None, "labels", "btn_adm_ops")
        _text, buttons = _shown(callback)
        self.assertEqual(buttons[-1], "adm:st:lab:admin")
        self.assertIn("adm:st:edit:btn_adm_orders", buttons)

    async def test_a_button_from_an_older_message_opens_the_group_in_its_new_place(self) -> None:
        callback = _callback()
        with patch.object(admin_settings, "get_all_settings", AsyncMock(return_value={})):
            await admin_settings._render_sub(callback, None, "shop", "btn_main")
        _text, buttons = _shown(callback)
        self.assertIn("adm:st:edit:btn_shop", buttons)
        self.assertEqual(buttons[-1], "adm:st:lab:user")

    async def test_moved_fields_open_in_their_new_sections(self) -> None:
        cases = {
            "referral_bonus": ("shop", "invite"),
            "terms_entry_text": ("limits", "terms"),
            "terms_buy_user_text": ("buy", "terms_buy"),
            "trial_require_contact": ("buy", "trial_gate"),
            "btn_main_menu_does_not_exist": None,
            "btn_shop": ("labels", "btn_main"),
        }
        for key, location in cases.items():
            with self.subTest(key=key):
                self.assertEqual(admin_settings._owner_screen_for_key(key), location)

    async def test_cancelling_a_label_edit_returns_to_its_group(self) -> None:
        with patch.object(admin_settings, "get_all_settings", AsyncMock(return_value={})):
            text, markup = await admin_settings._settings_location_panel(None, ("labels", "btn_main"))
        self.assertIn("adm:st:edit:btn_shop", _callbacks(markup))
        self.assertEqual(_callbacks(markup)[-1], "adm:st:lab:user")

    async def test_the_shop_settings_list_the_same_subjects(self) -> None:
        self.assertEqual(
            reseller_settings.HUB_ORDER,
            ["shop", "menu", "labels", "pay", "access", "limits", "buy", "support", "guides", "notify", "bot"],
        )
        self.assertEqual(reseller_settings.SECTIONS["buy"]["title"], admin_settings.SECTIONS["buy"]["title"])


class StoredLabelTests(unittest.TestCase):
    def test_untouched_section_names_follow_the_new_wording_and_edited_ones_stay(self) -> None:
        stored = {"btn_adm_st_shop": "فروشگاه", "btn_res_st_limits": "محدودیت", "btn_adm_st_pay": "💳 پول"}
        refreshed = refresh_retired_defaults(dict(stored), DEFAULT_SETTINGS)
        self.assertEqual(refreshed["btn_adm_st_shop"], "نام و متن‌ها")
        self.assertEqual(refreshed["btn_res_st_limits"], "ورود و عضویت")
        self.assertEqual(refreshed["btn_adm_st_pay"], "💳 پول")

    def test_hub_buttons_match_the_section_titles(self) -> None:
        from app.bot.keyboards import _admin_settings_submenu_entries, _reseller_settings_submenu_entries

        admin = [label for _key, label in _admin_settings_submenu_entries()][:-1]
        self.assertEqual(admin, [admin_settings.SECTIONS[sec]["title"] for sec in admin_settings.HUB_ORDER])
        shop = [label for _key, label in _reseller_settings_submenu_entries()][:-1]
        self.assertEqual(shop, [reseller_settings.SECTIONS[sec]["title"] for sec in reseller_settings.HUB_ORDER])


if __name__ == "__main__":
    unittest.main()
