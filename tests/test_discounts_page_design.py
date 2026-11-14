"""The discounts page follows the panel design language (page title, switch, table)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape

from app.services.formatting import format_money, format_number

ROOT = Path(__file__).resolve().parents[1]


def _render(**overrides) -> str:
    env = Environment(
        loader=ChoiceLoader(
            [
                DictLoader({"base.html": "{% block content %}{% endblock %}"}),
                FileSystemLoader(ROOT / "app/web/templates"),
            ]
        ),
        autoescape=select_autoescape(),
    )
    env.filters["num"] = format_number
    env.filters["money"] = format_money
    row = SimpleNamespace(
        id=1, title="<b>Eid</b>", scope="all", mode="timed", reduction_kind="percent",
        reduction_value=10, ends_at=True, is_active=True, campaign_id=5,
    )
    context = dict(
        request=SimpleNamespace(query_params={}),
        csrf_token="t",
        request_key="k",
        scopes={"all": "همه"},
        modes={"timed": "زمان‌دار"},
        plans=[],
        categories=[],
        discounts=[row],
        deadlines={1: "2026-01-01 10:00"},
        announcement_status={5: "running"},
        next_before=None,
    )
    context.update(overrides)
    return env.get_template("catalog_discounts.html").render(**context)


class DiscountsPageDesignTests(unittest.TestCase):
    def test_title_uses_page_title_with_icon(self) -> None:
        html = _render()
        self.assertIn('class="page-title"', html)
        self.assertIn("page-title-ico", html)
        self.assertRegex(html, r"<h1>تخفیف‌ها</h1>")

    def test_notify_option_is_a_switch_not_a_bare_checkbox(self) -> None:
        html = _render()
        self.assertIn("ui-switch-row", html)
        self.assertRegex(html, r'<span class="ui-switch">\s*<input type="checkbox" name="notify" value="1" checked')
        bare = [m for m in re.finditer(r'<label[^>]*>\s*<input type="checkbox"', html)]
        self.assertEqual(bare, [])

    def test_history_is_a_table_with_status_badges_and_escaped_titles(self) -> None:
        html = _render()
        self.assertIn("&lt;b&gt;Eid&lt;/b&gt;", html)
        self.assertNotIn("<b>Eid</b>", html)
        self.assertIn('class="badge ok"', html)
        self.assertIn('class="badge info"', html)
        self.assertIn('action="/catalog-discounts/1/stop"', html)

    def test_stopped_discount_has_no_stop_form(self) -> None:
        stopped = SimpleNamespace(
            id=2, title="old", scope="all", mode="timed", reduction_kind="amount",
            reduction_value=500, ends_at=None, is_active=False, campaign_id=None,
        )
        html = _render(discounts=[stopped])
        self.assertNotIn("/catalog-discounts/2/stop", html)
        self.assertIn("دائمی", html)

    def test_empty_history_shows_empty_state(self) -> None:
        self.assertIn("هنوز تغییری در قیمت ثبت نشده است.", _render(discounts=[]))


if __name__ == "__main__":
    unittest.main()
