"""Behavior of the built-in text inventory used to verify text moves."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.bot_copy_inventory import build_inventory, compare, strings_in_file

_SAMPLE_SOURCE = '''
"""ماژول نمونه — docstring is not user-facing."""

def handler(name):
    """راهنمای داخلی."""
    title = "کیف پول"
    greeting = f"سلام {name}، خوش آمدید"
    key = "wallet"
    return title, greeting, key, "کیف پول"
'''


class BotCopyInventoryTests(unittest.TestCase):
    def _write_tree(self, root: Path) -> None:
        handlers = root / "app" / "bot"
        handlers.mkdir(parents=True)
        (handlers / "sample.py").write_text(_SAMPLE_SOURCE, encoding="utf-8")

    def test_collects_persian_literals_and_fstring_parts_but_not_docstrings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_tree(root)
            found = strings_in_file(root / "app" / "bot" / "sample.py")
        self.assertEqual(sorted(found), sorted(["کیف پول", "کیف پول", "سلام ", "، خوش آمدید"]))

    def test_inventory_counts_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_tree(root)
            inventory = build_inventory(root)
        self.assertEqual(inventory["کیف پول"], 2)
        self.assertNotIn("wallet", inventory)

    def test_merged_duplicates_are_not_reported_as_text_changes(self) -> None:
        report = compare({"لغو شد.": 3}, {"لغو شد.": 1})
        self.assertEqual(report["added"], [])
        self.assertEqual(report["removed"], [])
        self.assertEqual(report["count_changed"], {"لغو شد.": {"before": 3, "after": 1}})

    def test_reworded_text_is_reported(self) -> None:
        report = compare({"لغو شد.": 1}, {"✖️ لغو شد.": 1})
        self.assertEqual(report["added"], ["✖️ لغو شد."])
        self.assertEqual(report["removed"], ["لغو شد."])


if __name__ == "__main__":
    unittest.main()
