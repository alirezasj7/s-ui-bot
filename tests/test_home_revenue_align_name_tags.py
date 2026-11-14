"""Home revenue RTL align + users name-column tag grid (2 per row)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HomeRevenueAlignTests(unittest.TestCase):
    def test_revenue_uses_ltr_span_not_dd_dir(self):
        home = (ROOT / "app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        finance = (ROOT / "app/web/templates/_finance_reports.html").read_text(
            encoding="utf-8"
        )
        for src in (home, finance):
            self.assertIn("<dt>درآمد</dt>", src)
            self.assertIn('<span dir="ltr">', src)
            self.assertNotIn('<dd dir="ltr">', src)

    def test_metrics_css_keeps_start_alignment(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".home-period-metrics dd {", 1)[1].split("}", 1)[0]
        self.assertIn("text-align: start", block)


class NameColumnTagGridTests(unittest.TestCase):
    def test_tags_two_column_grid(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        tags = css.split(".cell-name-tags {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(2, max-content)", tags)
        self.assertIn("display: grid", tags)
        col = css.split(".users-ops-table .col-name {", 1)[1].split("}", 1)[0]
        self.assertIn("min-width: 11.5rem", col)
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn("cell-name-tags", users)


if __name__ == "__main__":
    unittest.main()
