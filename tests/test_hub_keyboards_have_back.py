"""Every inline hub keyboard ends with a «بازگشت» row (except root hubs)."""

from __future__ import annotations

import inspect
import unittest

from aiogram.types import InlineKeyboardMarkup

from app.bot import nav_inline

ROOT_HUBS: frozenset[str] = frozenset()


def _hub_builders():
    for name, fn in inspect.getmembers(nav_inline, inspect.isfunction):
        if not name.endswith("_hub_keyboard") or name in ROOT_HUBS:
            continue
        required = [
            p
            for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(required) <= 1:
            yield name, fn, len(required)


class HubBackRowTests(unittest.TestCase):
    def test_hub_keyboards_end_with_back(self):
        checked = 0
        for name, fn, required in _hub_builders():
            markup = fn("users", {}) if required == 1 else fn({})
            if not isinstance(markup, InlineKeyboardMarkup):
                continue
            checked += 1
            last_row = markup.inline_keyboard[-1]
            self.assertTrue(
                any("بازگشت" in b.text for b in last_row),
                f"{name} has no back row",
            )
        self.assertGreater(checked, 8)


if __name__ == "__main__":
    unittest.main()
