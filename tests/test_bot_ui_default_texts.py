"""Safety net for the bot's built-in default texts and button labels.

Shops that never customized a text see the code default, so a broken default
reaches every such shop at once. These tests keep each default sendable
(valid Telegram HTML, known placeholders, within the message limit) and record
the exact wording in a snapshot so any rewording is reviewed as a diff.
"""

from __future__ import annotations

import re
import unittest

from app.services import bot_feedback_texts
from app.services.message_variables import all_vars, preview_fill_map
from app.services.rich_text import is_button_label_key
from app.services.users import DEFAULT_SETTINGS
from tests.bot_ui_snapshots import (
    MESSAGE_TEXT_MAX_CHARS,
    assert_matches_snapshot,
    telegram_html_errors,
)

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
# Settings whose value is structured data, not a message template.
_DATA_VALUED_KEYS = frozenset({"reply_btn_label_aliases", "wholesale_tiers"})


def _text_defaults() -> dict[str, str]:
    return {
        key: value
        for key, value in DEFAULT_SETTINGS.items()
        if not is_button_label_key(key) and key not in _DATA_VALUED_KEYS
    }


def _fixed_feedback_texts() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(bot_feedback_texts).items()
        if name.isupper() and isinstance(value, str)
    }


def _known_placeholders() -> frozenset[str]:
    names: set[str] = set()
    for var in all_vars():
        names.add(var.key)
        names.update(var.aliases)
    return frozenset(names)


def _with_sample_values(template: str) -> str:
    rendered = template
    for placeholder, example in preview_fill_map().items():
        rendered = rendered.replace(placeholder, example)
    return rendered


class DefaultTextSafetyTests(unittest.TestCase):
    def test_default_texts_are_valid_telegram_html(self) -> None:
        for key, value in _text_defaults().items():
            with self.subTest(key=key):
                self.assertEqual(telegram_html_errors(value), [])

    def test_default_texts_use_only_known_placeholders(self) -> None:
        known = _known_placeholders()
        for key, value in _text_defaults().items():
            with self.subTest(key=key):
                unknown = sorted(set(_PLACEHOLDER_RE.findall(value)) - known)
                self.assertEqual(unknown, [])

    def test_default_texts_fit_one_message_with_sample_values(self) -> None:
        for key, value in _text_defaults().items():
            with self.subTest(key=key):
                self.assertLessEqual(len(_with_sample_values(value)), MESSAGE_TEXT_MAX_CHARS)

    def test_default_button_labels_are_plain_non_empty_text(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            if not is_button_label_key(key):
                continue
            with self.subTest(key=key):
                self.assertTrue(value.strip())
                self.assertNotIn("<", value)


    def test_fixed_feedback_texts_are_valid_telegram_html(self) -> None:
        for name, value in _fixed_feedback_texts().items():
            with self.subTest(name=name):
                self.assertTrue(value.strip())
                self.assertEqual(telegram_html_errors(value), [])


class DefaultTextSnapshotTests(unittest.TestCase):
    def test_default_texts_match_reviewed_snapshot(self) -> None:
        assert_matches_snapshot(self, "default_texts", dict(DEFAULT_SETTINGS))

    def test_fixed_feedback_texts_match_reviewed_snapshot(self) -> None:
        assert_matches_snapshot(self, "feedback_texts", _fixed_feedback_texts())


if __name__ == "__main__":
    unittest.main()
