"""Modal section-tabs must scroll horizontally with wheel/trackpad."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ModalTabsScrollTests(unittest.TestCase):
    def test_wheel_guard_maps_to_modal_tabs(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("function tryScrollModalTabs", js)
        self.assertIn("tryScrollModalTabs(e, modal)", js)
        self.assertIn(".modal-section-tabs", js)
        # Touch over overflowing tabs must not be preventDefault'd.
        self.assertIn("Let native horizontal pan work on overflowing modal tab strips", js)

    def test_modal_tabs_css_overflow(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css[
            css.find(".settings-modal-panel > .modal-section-tabs") : css.find(
                ".settings-modal-body"
            )
        ]
        self.assertIn("flex-wrap: nowrap", block)
        self.assertIn("overflow-x: auto", block)
        self.assertIn("touch-action: pan-x", block)

    def test_loyalty_modal_uses_modal_section_tabs(self):
        html = (ROOT / "app/web/templates/_modal_loyalty_settings.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("modal-section-tabs", html)
        self.assertIn("data-modal-tabs", html)


if __name__ == "__main__":
    unittest.main()
