"""The screen registry reports exactly the settings behind each button it lists.

The editor will change a setting and expect one specific button on one
specific screen to change. These tests change each reported setting and check
that the matching button, and only buttons tied to the same setting, change.
"""

from __future__ import annotations

import re
import unittest

from app.bot.button_sources import is_recording, note_button_source, recording_button_sources
from app.bot.screen_registry import (
    SCREEN_ID_MAX_LENGTH,
    SCREENS,
    ScreenButton,
    ScreenContext,
    screen_buttons,
)
from app.services.button_styles import style_ids_sharing_setting
from app.services.rich_text import is_button_label_key
from app.services.users import DEFAULT_SETTINGS
from tests.bot_ui_snapshots import dump_markup
from tests.test_bot_ui_keyboard_snapshots import default_ui, sample_reseller_profile

_PROBE_LABEL = "🧪 برچسب آزمایشی"
_COLORS = ("primary", "success", "danger", "")
_SCREEN_ID_RE = re.compile(r"^[a-z]\.[a-z0-9_.]+$")
_LABEL_SETTINGS = sorted(key for key in DEFAULT_SETTINGS if is_button_label_key(key))
_STYLE_SETTINGS = sorted(key for key in DEFAULT_SETTINGS if key.startswith("btn_style_"))


def _context(ui: dict[str, str] | None = None) -> ScreenContext:
    return ScreenContext(ui=ui if ui is not None else default_ui(), profile=sample_reseller_profile())


def _by_position(buttons: list[ScreenButton]) -> dict[tuple[int, int], ScreenButton]:
    return {(button.row, button.column): button for button in buttons}


def _other_color(current: str) -> str:
    return next(color for color in _COLORS if color != current)


class ScreenRegistryShapeTests(unittest.TestCase):
    def test_screen_ids_are_short_and_stable_shaped(self) -> None:
        for screen_id, spec in SCREENS.items():
            with self.subTest(screen=screen_id):
                self.assertEqual(spec.id, screen_id)
                self.assertLessEqual(len(screen_id.encode("utf-8")), SCREEN_ID_MAX_LENGTH)
                self.assertRegex(screen_id, _SCREEN_ID_RE)
                self.assertTrue(spec.title.strip())

    def test_every_screen_offers_something_to_edit(self) -> None:
        for screen_id in SCREENS:
            with self.subTest(screen=screen_id):
                self.assertTrue(any(b.is_editable for b in screen_buttons(screen_id, _context())))

    def test_reported_settings_exist(self) -> None:
        for screen_id in SCREENS:
            for button in screen_buttons(screen_id, _context()):
                with self.subTest(screen=screen_id, button=button.text):
                    if button.label_key:
                        self.assertIn(button.label_key, DEFAULT_SETTINGS)
                    if button.style_id:
                        self.assertIn(button.style_setting_key, DEFAULT_SETTINGS)

    def test_unknown_screen_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            screen_buttons("x.missing", _context())

    def test_lists_every_button_of_the_real_keyboard_in_order(self) -> None:
        for screen_id, spec in SCREENS.items():
            markup = dump_markup(spec.build(_context()))
            rows = markup.get("inline_keyboard") or markup.get("keyboard")
            expected = [button["text"] for row in rows for button in row]
            with self.subTest(screen=screen_id):
                self.assertEqual([b.text for b in screen_buttons(screen_id, _context())], expected)


class ScreenRegistryPrecisionTests(unittest.TestCase):
    """Every setting is changed in turn; only the buttons the registry ties to it may move."""

    def test_each_label_setting_changes_exactly_the_buttons_tied_to_it(self) -> None:
        for screen_id in SCREENS:
            before = screen_buttons(screen_id, _context())
            for key in _LABEL_SETTINGS:
                ui = default_ui()
                ui[key] = _PROBE_LABEL
                after = _by_position(screen_buttons(screen_id, _context(ui)))
                for button in before:
                    changed = after[(button.row, button.column)].text
                    tied = button.label_key == key
                    if tied == changed.startswith(_PROBE_LABEL) and (tied or changed == button.text):
                        continue
                    self.fail(f"{screen_id}: «{button.text}» vs setting {key}: tied={tied}, now «{changed}»")

    def test_each_color_setting_changes_exactly_the_buttons_tied_to_it(self) -> None:
        for screen_id, spec in SCREENS.items():
            before = screen_buttons(screen_id, _context())
            before_dump = dump_markup(spec.build(_context()))
            for setting in _STYLE_SETTINGS:
                current = default_ui()[setting]
                for color in [c for c in _COLORS if c != current][:2]:
                    ui = default_ui()
                    ui[setting] = color
                    after_dump = dump_markup(spec.build(_context(ui)))
                    for button in before:
                        old = _button_at(before_dump, button).get("style", "")
                        new = _button_at(after_dump, button).get("style", "")
                        expected = color if button.style_setting_key == setting else old
                        if new != expected:
                            self.fail(
                                f"{screen_id}: «{button.text}» with {setting}={color!r}: "
                                f"style {new!r}, expected {expected!r}"
                            )

    def test_shared_color_settings_are_reported(self) -> None:
        self.assertIn("rev_ok", style_ids_sharing_setting("confirm"))
        self.assertIn("confirm", style_ids_sharing_setting("rev_ok"))
        self.assertEqual(style_ids_sharing_setting("wallet_topup"), ("wallet_topup",))


def _button_at(dumped: dict, button: ScreenButton) -> dict:
    rows = dumped.get("inline_keyboard") or dumped.get("keyboard")
    return rows[button.row][button.column]


class ButtonSourceRecordingTests(unittest.TestCase):
    def test_recording_does_not_change_the_keyboard(self) -> None:
        for screen_id, spec in SCREENS.items():
            plain = dump_markup(spec.build(_context()))
            with recording_button_sources():
                recorded = dump_markup(spec.build(_context()))
            with self.subTest(screen=screen_id):
                self.assertEqual(recorded, plain)

    def test_nothing_is_kept_outside_a_recording(self) -> None:
        self.assertFalse(is_recording())
        marker = object()
        note_button_source(marker, label_key="btn_wallet", style_id="wallet")
        with recording_button_sources() as log:
            self.assertTrue(is_recording())
            self.assertIsNone(log.source_of(marker))
        self.assertFalse(is_recording())

    def test_recordings_do_not_leak_into_each_other(self) -> None:
        first, second = object(), object()
        with recording_button_sources() as outer:
            note_button_source(first, label_key="btn_wallet", style_id=None)
            with recording_button_sources() as inner:
                note_button_source(second, label_key=None, style_id="wallet")
            self.assertIsNone(outer.source_of(second))
            self.assertIsNone(inner.source_of(first))
            self.assertEqual(outer.source_of(first).label_key, "btn_wallet")


if __name__ == "__main__":
    unittest.main()
