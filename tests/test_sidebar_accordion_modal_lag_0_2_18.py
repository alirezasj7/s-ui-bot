"""v0.2.18 — sidebar accordion color flash + modal close jump."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
NAV = (ROOT / "app/web/static/panel-nav-modes.css").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")


class AccordionFlashTests(unittest.TestCase):
    def test_nav_sections_do_not_transition_background(self):
        marker = "/* Instant collapsed/open fill"
        self.assertIn(marker, CSS)
        self.assertIn("transition: none", CSS.split(marker, 1)[1].split("}", 1)[0] + "}")
        # Old fade must not remain on the shared section rule.
        shared = CSS.split(".nav-section-bot,", 1)[1].split(".nav-section-home {", 1)[0]
        self.assertNotIn("background var(--motion-fast)", shared)

    def test_nav_label_toggle_no_background_transition(self):
        self.assertIn("transition: none", NAV)
        # Must not keep the old multi-property background fade on the toggle.
        self.assertNotIn(
            "background var(--motion-fast, 0.15s)",
            NAV,
        )

    def test_scroll_into_view_only_visible_active(self):
        start = JS.index("function setOpenSections")
        end = JS.index("setOpenSections(rules.defaultOpenKeys", start)
        body = JS[start:end]
        self.assertIn(":not(.is-collapsed) .nav-item.active", body)


class ModalCloseJumpTests(unittest.TestCase):
    def test_finish_close_blurs_focus_inside_modal(self):
        start = JS.index("function finishCloseModal")
        end = JS.index("function closeModal", start)
        body = JS[start:end]
        self.assertIn("activeElement", body)
        self.assertIn("blur", body)
        self.assertIn("el.contains(ae)", body)


class TopbarAboveDrawerRegressionTests(unittest.TestCase):
    def test_nav_open_raises_topbar(self):
        self.assertIn("body.nav-open .topbar", CSS)
        self.assertNotIn("body.nav-open .menu-toggle", CSS)


if __name__ == "__main__":
    unittest.main()
