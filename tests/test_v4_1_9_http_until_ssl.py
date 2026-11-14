"""v4.1.9 — HTTP until SSL live; SSL success modal."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class HttpUntilSslTests(unittest.TestCase):
    def test_https_is_active_helper(self):
        src = (ROOT / "app/services/ssl_certs.py").read_text(encoding="utf-8")
        self.assertIn("def https_is_active", src)
        self.assertIn("def public_panel_base_url", src)

    def test_default_panel_base_uses_http_when_ssl_off(self):
        src = (ROOT / "app/services/setup_wizard.py").read_text(encoding="utf-8")
        self.assertIn("https_is_active", src)
        self.assertIn("default_http_panel_url", src)

    def test_panel_redirect_in_app(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("def _panel_redirect", src)
        self.assertIn("_panel_redirect(request, home)", src)

    def test_ssl_template_success_modal(self):
        html = (ROOT / "app/web/templates/_settings_ssl.html").read_text(encoding="utf-8")
        self.assertIn("ssl-done-modal", html)
        self.assertIn("ورود به پنل (HTTPS)", html)
        self.assertNotIn("location.href = url + '/settings", html)
        self.assertNotIn("restarting') == '1'", html)

    def test_setup_finish_always_http(self):
        from app.services.setup_wizard import setup_finish_login_url

        with patch("app.services.setup_wizard.detect_server_ip", return_value="10.0.0.1"), patch(
            "app.config.get_settings"
        ) as gs:
            gs.return_value.web_port = 9000
            url = setup_finish_login_url()
        self.assertEqual(url, "http://10.0.0.1:9000/login?restarting=1")


if __name__ == "__main__":
    unittest.main()
