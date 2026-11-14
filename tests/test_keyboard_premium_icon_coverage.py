"""Every editable button label with a premium emoji must reach Telegram as an icon."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

from aiogram.types import InlineKeyboardMarkup, MessageEntity, ReplyKeyboardMarkup

from app.bot import keyboards, nav_inline, reply_keyboards
from app.bot.handlers.guides import guide_detail_keyboard
from app.bot.keyboards import (
    admin_plans_add_type_keyboard,
    admin_users_plans_overview_keyboard,
    category_icon_for,
    plans_keyboard,
    wholesale_plans_keyboard,
)
from app.services.rich_text import (
    btn_setting_key_for_action,
    button_display_text,
    is_button_label_key,
    pack_rich_text,
)
from app.services.users import DEFAULT_SETTINGS

# Hard-coded hub labels that only coincide with an unrelated editable label.
COINCIDENTAL_LABELS = {"🎁 جوایز", "👥 کاربران"}


def _all_labels_packed() -> tuple[dict, dict[str, str]]:
    ui = dict(DEFAULT_SETTINGS)
    labels: dict[str, str] = {}
    for index, (key, value) in enumerate(list(ui.items())):
        if is_button_label_key(key) and isinstance(value, str) and value.strip():
            entity = MessageEntity(
                type="custom_emoji", offset=0, length=1, custom_emoji_id=str(1000 + index)
            )
            ui[key] = pack_rich_text("★" + value, [entity])
            labels[button_display_text(ui[key]).strip()] = key
    for flag in (
        "pay_wallet_enabled", "pay_card_enabled", "pay_gateway_enabled", "pay_psp_enabled",
        "pay_crypto_enabled", "pay_stars_enabled", "pay_discount_enabled",
        "trial_enabled", "custom_plan_enabled", "wholesale_enabled",
    ):
        ui[flag] = "1"
    return ui, labels


def _buttons(markup: object) -> list:
    if isinstance(markup, InlineKeyboardMarkup):
        return [b for row in markup.inline_keyboard for b in row]
    if isinstance(markup, ReplyKeyboardMarkup):
        return [b for row in markup.keyboard for b in row]
    return []


class PremiumIconCoverageTests(unittest.TestCase):
    def test_every_ui_only_builder_shows_icon_for_editable_labels(self) -> None:
        ui, labels = _all_labels_packed()
        missing: list[tuple[str, str]] = []
        for module in (keyboards, nav_inline, reply_keyboards):
            for name, builder in inspect.getmembers(module, inspect.isfunction):
                params = inspect.signature(builder).parameters
                if builder.__module__ != module.__name__ or any(
                    p.default is inspect.Parameter.empty and pn != "ui"
                    for pn, p in params.items()
                ):
                    continue
                markup = builder(ui=ui) if "ui" in params else builder()
                for button in _buttons(markup):
                    text = (button.text or "").strip()
                    if (
                        text in labels
                        and text not in COINCIDENTAL_LABELS
                        and not getattr(button, "icon_custom_emoji_id", None)
                        and not getattr(button, "web_app", None)
                    ):
                        missing.append((f"{module.__name__}.{name}", text))
        self.assertEqual(missing, [])

    def test_reply_actions_resolve_to_their_editable_label_keys(self) -> None:
        self.assertEqual(btn_setting_key_for_action("svc_guide"), "btn_guides")
        self.assertEqual(btn_setting_key_for_action("res_preview"), "btn_adm_preview")


class PlanIconInheritanceTests(unittest.TestCase):
    def test_category_icon_for_handles_missing_category(self) -> None:
        plan = SimpleNamespace(category_id=3)
        self.assertIsNone(category_icon_for(plan, None))
        self.assertIsNone(category_icon_for(plan, {9: SimpleNamespace(icon_custom_emoji_id="1")}))
        self.assertEqual(
            category_icon_for(plan, {3: SimpleNamespace(icon_custom_emoji_id="77")}), "77"
        )

    def test_wholesale_plan_buttons_inherit_category_icon(self) -> None:
        plan = SimpleNamespace(
            id=1, name="A", price=1, category_id=3, button_style=None, is_trial=False
        )
        markup = wholesale_plans_keyboard(
            [plan], {}, categories={3: SimpleNamespace(icon_custom_emoji_id="77")}
        )
        self.assertEqual(markup.inline_keyboard[0][0].icon_custom_emoji_id, "77")

    def test_plan_buttons_without_category_icon_stay_text_only(self) -> None:
        plan = SimpleNamespace(
            id=1, name="A", price=1, category_id=3, button_style=None, is_trial=False
        )
        markup = plans_keyboard(
            [plan], {}, categories={3: SimpleNamespace(icon_custom_emoji_id=None, button_style=None)}
        )
        self.assertIsNone(markup.inline_keyboard[0][0].icon_custom_emoji_id)


class ExplicitIconWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui, _labels = _all_labels_packed()
        for index, key in enumerate(
            ("btn_shop_kind_fixed", "btn_shop_kind_custom", "btn_shop_kind_trial")
        ):
            entity = MessageEntity(
                type="custom_emoji", offset=0, length=1, custom_emoji_id=str(9000 + index)
            )
            self.ui[key] = pack_rich_text("★ برچسب", [entity])

    def test_guide_open_link_button_has_icon(self) -> None:
        markup = guide_detail_keyboard(
            {"deep_link": True}, self.ui, sub_url="https://example.com/sub/token"
        )
        link = markup.inline_keyboard[0][0]
        self.assertTrue(link.icon_custom_emoji_id)

    def test_admin_add_plan_type_and_overview_kind_buttons_have_icons(self) -> None:
        add_type = admin_plans_add_type_keyboard("users", self.ui)
        overview = admin_users_plans_overview_keyboard([], self.ui)
        for markup in (add_type, overview):
            kind_buttons = [
                b for b in _buttons(markup)
                if (b.callback_data or "").rsplit(":", 1)[-1] in {"fixed", "custom", "trial", "wholesale"}
            ]
            self.assertTrue(kind_buttons)
            self.assertTrue(all(b.icon_custom_emoji_id for b in kind_buttons))

    def test_cancel_reply_keyboard_has_icon_and_keeps_matching_text(self) -> None:
        button = _buttons(reply_keyboards.cancel_reply(self.ui))[0]
        self.assertEqual(button.text, "انصراف")
        self.assertTrue(button.icon_custom_emoji_id)


if __name__ == "__main__":
    unittest.main()
