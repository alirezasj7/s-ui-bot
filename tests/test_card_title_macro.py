"""Dashboard card titles carry a line icon in the tone of their section."""

from __future__ import annotations

import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parents[1] / "app/web/templates"
ICONS = ("payments", "orders", "connection", "wallet", "queue", "sales", "limits")


def _render(source: str) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)
    return env.from_string('{% from "macros.html" import card_title %}' + source).render()


class CardTitleMacroTests(unittest.TestCase):
    def test_every_icon_name_draws_a_shape(self) -> None:
        for name in ICONS:
            with self.subTest(icon=name):
                html = _render("{{ card_title('%s', 'عنوان') }}" % name)
                self.assertIn("<h2", html)
                self.assertRegex(html, r"<svg[^>]*>\s*<(path|rect|circle)")

    def test_tone_selects_the_colour_class_and_text_is_escaped(self) -> None:
        bot = _render("{{ card_title('payments', 'x', 'bot') }}")
        neutral = _render("{{ card_title('wallet', '<b>x</b>') }}")
        self.assertIn("card-title--bot", bot)
        self.assertIn("card-title--neutral", neutral)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", neutral)

    def test_dashboard_templates_still_parse(self) -> None:
        env = Environment(loader=FileSystemLoader(TEMPLATES))
        for name in ("dashboard.html", "_home_dash_body.html", "_reseller_home_dash_body.html", "_home_ops.html", "_pg_limit_cards.html"):
            with self.subTest(template=name):
                env.parse((TEMPLATES / name).read_text(encoding="utf-8"))
