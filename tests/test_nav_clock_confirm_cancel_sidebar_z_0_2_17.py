"""v0.2.17 — confirm cancel must not leave nav clock; sidebar above ported menus."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class ConfirmCancelNavClockTests(unittest.TestCase):
    def test_submit_listener_skips_data_confirm(self):
        """Capture-phase arm must not run for confirm-gated forms (cancel stuck clock)."""
        self.assertIn("data-confirm", JS)
        self.assertIn("confirm-form", JS)
        # Narrow to the nav-clock submit listener body.
        start = JS.index("Lightweight nav clock")
        end = JS.index("Permanent no-zoom", start)
        body = JS[start:end]
        self.assertIn("form.hasAttribute('data-confirm')", body)
        self.assertIn("form.id === 'confirm-form'", body)
        self.assertIn("return;", body)

    def test_submit_form_post_arms_clock(self):
        """Real POST after confirm OK arms the clock (fetch path has no submit event)."""
        start = JS.index("function submitFormPost")
        end = JS.index("function submitFormWithCsrf", start)
        body = JS[start:end]
        self.assertIn("armPanelNavClock()", body)

    def test_confirm_cancel_disarms_clock(self):
        start = JS.index("function finish(result)")
        end = JS.index("window.panelConfirm", start)
        body = JS[start:end]
        self.assertIn("disarmPanelNavClock", body)
        self.assertIn("!result.ok", body)

    def test_confirm_backdrop_cancel_uses_finish(self):
        """Cancel click must go through finish (disarm + resolve), not a bare resolver."""
        start = JS.index("modal.addEventListener('click'")
        end = JS.index("document.addEventListener('keydown'", start)
        body = JS[start:end]
        self.assertIn("finish({ ok: false })", body)
        self.assertNotIn("resolver = null", body)


class SidebarAbovePortedMenusTests(unittest.TestCase):
    def test_nav_open_raises_drawer_z_index(self):
        self.assertIn("body.nav-open .side-backdrop", CSS)
        self.assertIn("body.nav-open .side", CSS)
        # Whole topbar must rise — menu-toggle alone stays trapped in topbar's context.
        self.assertIn("body.nav-open .topbar", CSS)
        self.assertIn("z-index: 5100", CSS)
        self.assertIn("z-index: 5200", CSS)
        self.assertIn("z-index: 5300", CSS)
        # Regression: bumping only the toggle covered the header under the drawer.
        self.assertNotIn("body.nav-open .menu-toggle", CSS)

    def test_opening_drawer_closes_ported_menus(self):
        start = JS.index("function setOpen(v, instant)")
        end = JS.index("setOpen(false);", start)
        body = JS[start:end]
        self.assertIn("closeUiSelects", body)
        self.assertIn("closeRowActions", body)
        self.assertIn("if (open)", body)


if __name__ == "__main__":
    unittest.main()
