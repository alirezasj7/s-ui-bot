"""Lazy Telegram settings preview — closed until user opens it."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
CHAT = ROOT / "app/web/templates/_tg_preview_chat.html"
CHAT_JS = ROOT / "app/web/templates/_tg_preview_chat_js.html"
APPEAR = ROOT / "app/web/templates/_tg_preview_appearance.html"
APPEAR_JS = ROOT / "app/web/templates/_tg_preview_appearance_js.html"
SETTINGS = ROOT / "app/web/templates/settings.html"
SHOP = ROOT / "app/web/templates/shop_settings.html"


class LazyPreviewMarkupTests(unittest.TestCase):
    def test_gate_and_hidden_panel(self):
        for path in (CHAT, APPEAR):
            html = path.read_text(encoding="utf-8")
            self.assertIn("data-tg-preview-gate", html)
            self.assertIn("data-tg-preview-open", html)
            self.assertIn("data-tg-preview-close", html)
            self.assertIn('data-tg-preview-panel hidden', html)
            self.assertIn("tg-preview-gate", html)
            self.assertIn("tg-preview-card", html)
            # Open/close swap inside the same card — gate is not a separate card
            self.assertNotIn("card settings-card tg-preview-gate", html)
            self.assertIn("tg-preview-close-btn", html)

    def test_layouts_start_without_has_preview(self):
        for path in (SETTINGS, SHOP):
            src = path.read_text(encoding="utf-8")
            self.assertIn("can-preview", src)
            # Class is added by JS on open — not baked in by default
            self.assertNotIn("has-preview{% endif %}", src)
            self.assertNotIn('class="settings-layout has-preview', src)


class LazyPreviewJsTests(unittest.TestCase):
    def test_chat_js_activates_on_open_only(self):
        js = CHAT_JS.read_text(encoding="utf-8")
        self.assertIn("function openPreview", js)
        self.assertIn("function closePreview", js)
        self.assertIn("DEBOUNCE_MS", js)
        self.assertIn("layout.classList.add('has-preview')", js)
        self.assertIn("layout.classList.remove('has-preview')", js)
        self.assertIn("bindLive", js)
        self.assertIn("unbindLive", js)
        # Must not auto-run render at load
        self.assertNotIn("\n  render();\n  const active", js)

    def test_appearance_js_activates_on_open_only(self):
        js = APPEAR_JS.read_text(encoding="utf-8")
        self.assertIn("function openPreview", js)
        self.assertIn("function closePreview", js)
        self.assertIn("DEBOUNCE_MS", js)
        self.assertNotRegex(js, r"(?m)^  render\(\);\s*\}\)\(\);")


class LazyPreviewCssTests(unittest.TestCase):
    def test_sticky_only_when_preview_open(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".settings-layout.has-preview .tg-preview-wrap", css)
        block = css.split(".settings-layout.has-preview .tg-preview-wrap {", 1)[1].split("}", 1)[0]
        self.assertIn("position: sticky;", block)
        self.assertIn(".tg-preview-gate", css)
        self.assertIn(".tg-preview-toolbar", css)
        self.assertIn(".tg-preview-close-btn", css)
        # Close control stretches full width (esp. mobile)
        self.assertIn("width: 100%", css.split(".tg-preview-toolbar", 1)[1].split(".tg-preview-wrap", 1)[0])
        # Open button also full-width on mobile (nested gate .actions)
        self.assertIn("tg-preview-gate > .actions", css)
        mobile_actions = css.split("/* Primary action rows:", 1)[1].split(".search-bar {", 1)[0]
        self.assertIn("tg-preview-gate > .actions", mobile_actions)
        self.assertIn("tg-preview-gate > .actions > .btn", mobile_actions)


if __name__ == "__main__":
    unittest.main()
