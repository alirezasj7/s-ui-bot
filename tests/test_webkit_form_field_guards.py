"""Guards against WebKit dropping critical panel form fields."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/panel.js"
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"


class WebkitFormFieldGuards(unittest.TestCase):
    def test_ui_select_mirrors_value_to_hidden(self):
        js = JS.read_text(encoding="utf-8")
        block = js.split("function enhanceSelect", 1)[1].split("function enhanceAllSelects", 1)[0]
        self.assertIn("data-ui-select-mirror", block)
        self.assertIn("removeAttribute('name')", block)
        self.assertIn("syncMirror", block)
        self.assertIn(".ui-select-native", CSS.read_text(encoding="utf-8"))

    def test_kebab_native_posts_use_submit_form_post(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("row-actions-menu, .row-actions", js)
        self.assertIn("panelSubmitFormPost(form, {})", js)

    def test_inbox_mode_not_submitted_via_clipped_radios(self):
        base = BASE.read_text(encoding="utf-8")
        dismiss = base.split('id="form-inbox-dismiss"', 1)[1].split("modal-confirm", 1)[0]
        self.assertIn('id="inbox-dismiss-mode"', dismiss)
        self.assertIn('name="mode"', dismiss)
        self.assertNotIn('name="mode_ui"', dismiss)
        # Radios are visual-only (data-inbox-mode), not named submit fields
        self.assertIn('data-inbox-mode="24h"', dismiss)
        self.assertIn('data-inbox-mode="forever"', dismiss)

    def test_no_zero_size_inbox_radios(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".inbox-dismiss-option input {", 1)[1].split("}", 1)[0]
        self.assertNotIn("width: 0;", block)
        self.assertNotIn("height: 0;", block)


if __name__ == "__main__":
    unittest.main()
