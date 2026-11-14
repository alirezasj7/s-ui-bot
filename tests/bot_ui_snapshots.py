"""Shared helpers for the bot UI safety-net tests.

The tests render keyboards and default texts, serialize them to plain JSON and
compare the result with a reviewed snapshot under ``tests/fixtures/bot_ui``.
A wording or layout change then shows up as a readable diff in review instead
of reaching customers unnoticed.

Regenerate snapshots after an intentional change::

    UPDATE_BOT_UI_SNAPSHOTS=1 python -m pytest tests/test_bot_ui_*.py -q
"""

from __future__ import annotations

import difflib
import json
import os
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

SNAPSHOT_DIR = Path(__file__).resolve().parent / "fixtures" / "bot_ui"
UPDATE_ENV = "UPDATE_BOT_UI_SNAPSHOTS"

# Telegram Bot API limits.
CALLBACK_DATA_MAX_BYTES = 64
MESSAGE_TEXT_MAX_CHARS = 4096
INLINE_KEYBOARD_MAX_BUTTONS = 100

# Tags and attributes accepted by Telegram's HTML parse mode.
_TELEGRAM_TAG_ATTRS: dict[str, frozenset[str]] = {
    "b": frozenset(),
    "strong": frozenset(),
    "i": frozenset(),
    "em": frozenset(),
    "u": frozenset(),
    "ins": frozenset(),
    "s": frozenset(),
    "strike": frozenset(),
    "del": frozenset(),
    "span": frozenset({"class"}),
    "tg-spoiler": frozenset(),
    "a": frozenset({"href"}),
    "tg-emoji": frozenset({"emoji-id"}),
    "code": frozenset({"class"}),
    "pre": frozenset(),
    "blockquote": frozenset({"expandable"}),
}
_TELEGRAM_NAMED_ENTITIES = frozenset({"lt", "gt", "amp", "quot"})

_INLINE_ACTION_FIELDS = (
    "callback_data",
    "url",
    "web_app",
    "login_url",
    "switch_inline_query",
    "switch_inline_query_current_chat",
    "switch_inline_query_chosen_chat",
    "copy_text",
    "callback_game",
    "pay",
)


def update_requested() -> bool:
    return os.environ.get(UPDATE_ENV, "").strip() in {"1", "true", "yes"}


def dump_markup(markup: InlineKeyboardMarkup | ReplyKeyboardMarkup) -> dict[str, Any]:
    """Every field Telegram receives, so any visible change shows in the diff."""
    data = markup.model_dump(mode="json", exclude_none=True)
    data["kind"] = "inline" if isinstance(markup, InlineKeyboardMarkup) else "reply"
    return data


def inline_buttons(markup: InlineKeyboardMarkup) -> list[Any]:
    return [button for row in markup.inline_keyboard for button in row]


def reply_buttons(markup: ReplyKeyboardMarkup) -> list[Any]:
    return [button for row in markup.keyboard for button in row]


def inline_action_fields(button: Any) -> list[str]:
    return [name for name in _INLINE_ACTION_FIELDS if getattr(button, name, None) is not None]


def _render(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def assert_matches_snapshot(test: unittest.TestCase, name: str, data: dict[str, Any]) -> None:
    """Compare *data* with ``fixtures/bot_ui/<name>.json`` (or rewrite it on request)."""
    path = SNAPSHOT_DIR / f"{name}.json"
    rendered = _render(data)
    if update_requested():
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    if not path.exists():
        test.fail(f"missing snapshot {path.name}; run with {UPDATE_ENV}=1 to create it")
    expected = path.read_text(encoding="utf-8")
    if expected == rendered:
        return
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"{path.name} (snapshot)",
            tofile=f"{path.name} (current)",
            n=2,
        )
    )
    test.fail(
        f"bot UI changed versus {path.name}. If the change is intended, review it and "
        f"rerun with {UPDATE_ENV}=1.\n{diff}"
    )


def load_snapshot(name: str) -> dict[str, Any]:
    path = SNAPSHOT_DIR / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_snapshot(name: str, data: dict[str, Any]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_DIR / f"{name}.json").write_text(_render(data), encoding="utf-8")


class _TelegramHtmlChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.errors: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        allowed = _TELEGRAM_TAG_ATTRS.get(tag)
        if allowed is None:
            self.errors.append(f"unsupported tag <{tag}>")
            return
        for attr, _value in attrs:
            if attr not in allowed:
                self.errors.append(f"unsupported attribute {attr!r} on <{tag}>")
        self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.errors.append(f"self-closing tag <{tag}/> is not supported")

    def handle_endtag(self, tag: str) -> None:
        if not self._open or self._open[-1] != tag:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        self._open.pop()

    def handle_data(self, data: str) -> None:
        for char in "<>&":
            if char in data:
                self.errors.append(f"unescaped {char!r} in text")

    def handle_entityref(self, name: str) -> None:
        if name not in _TELEGRAM_NAMED_ENTITIES:
            self.errors.append(f"unsupported entity &{name};")

    def handle_comment(self, data: str) -> None:
        self.errors.append("HTML comments are not supported")

    def close(self) -> None:
        super().close()
        if self.rawdata:
            self.errors.append(f"unterminated markup {self.rawdata[:20]!r}")
        for tag in self._open:
            self.errors.append(f"unclosed tag <{tag}>")


def telegram_html_errors(text: str) -> list[str]:
    """Problems that make Telegram reject *text* when sent with parse_mode=HTML."""
    checker = _TelegramHtmlChecker()
    checker.feed(text)
    checker.close()
    return checker.errors
