"""Unit tests for shared list pagination helpers."""

from __future__ import annotations

import unittest

from app.services.list_query import (
    DEFAULT_LIST_PAGE_SIZE,
    build_list_pager,
    extract_list_total,
    list_offset,
    parse_list_page,
)


class ListPagerTests(unittest.TestCase):
    def test_parse_and_offset(self):
        self.assertEqual(parse_list_page(None), 1)
        self.assertEqual(parse_list_page("0"), 1)
        self.assertEqual(parse_list_page("3"), 3)
        self.assertEqual(parse_list_page("x"), 1)
        self.assertEqual(list_offset(1, 50), 0)
        self.assertEqual(list_offset(2, 50), 50)
        self.assertEqual(DEFAULT_LIST_PAGE_SIZE, 50)

    def test_extract_total(self):
        self.assertEqual(extract_list_total({"users": [], "total": 120}), 120)
        self.assertEqual(extract_list_total({"count": 4}), 4)
        self.assertIsNone(extract_list_total([]))
        self.assertIsNone(extract_list_total({"users": []}))

    def test_pager_with_total(self):
        p = build_list_pager(page=2, page_size=50, fetched=50, total=120)
        self.assertEqual(p["pages"], 3)
        self.assertTrue(p["has_prev"])
        self.assertTrue(p["has_next"])
        self.assertEqual(p["prev_page"], 1)
        self.assertEqual(p["next_page"], 3)

    def test_pager_clears_total_when_scoped(self):
        p = build_list_pager(
            page=1, page_size=50, fetched=50, total=200, scoped_len=12
        )
        self.assertIsNone(p["total"])
        self.assertIsNone(p["pages"])
        self.assertTrue(p["has_next"])  # full API window
        self.assertFalse(p["has_prev"])

    def test_pager_last_partial_page(self):
        p = build_list_pager(page=3, page_size=50, fetched=20, total=None)
        self.assertFalse(p["has_next"])
        self.assertTrue(p["has_prev"])


if __name__ == "__main__":
    unittest.main()
