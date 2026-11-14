"""Update page UI styling and the force-join channel editor."""

from __future__ import annotations

import unittest
from pathlib import Path


class UpdateUiSourceTests(unittest.TestCase):
    def test_channel_select_keeps_its_rtl_chevron_styling(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".update-field-row", css)
        self.assertIn(".update-field ", css)
        field = css.split(".update-field select {", 1)[1].split("}", 1)[0]
        self.assertIn("text-align: right", field)
        self.assertIn("padding-left: var(--space-4)", field)
        self.assertIn("background-position: left var(--space-2) center", field)

    def test_force_channels_match_settings_pattern(self):
        html = Path("app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertNotIn("force-channels-footer", html)
        self.assertIn("force-channels-head", html)
        self.assertIn("force-channels-title", html)
        self.assertIn("force-channel-id-wrap", js)
        self.assertIn("force-channel-row", js)
        self.assertIn("force-channel-remove", js)
        self.assertIn("force-channel-add", js)
        self.assertIn("addTileHtml", js)
        self.assertIn(".force-channel-row", css)
        self.assertIn(".force-channel-add", css)
        self.assertNotIn(".force-channels-footer", css)
        self.assertIn("btn-danger", js)


if __name__ == "__main__":
    unittest.main()
