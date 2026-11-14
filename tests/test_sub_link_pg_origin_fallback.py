"""Path-only /sub/… links fall back to PasarGuard panel origin (no UI path)."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class PublicPgSubOriginTests(unittest.TestCase):
    def test_strips_dashboard_path(self):
        from app.services.pasarguard import public_pg_sub_origin

        with patch("app.services.pasarguard._pg", None), patch(
            "app.services.pasarguard.get_settings"
        ) as gs:
            gs.return_value.pg_base_url = "https://pg.example.com/MrClock"
            self.assertEqual(public_pg_sub_origin(), "https://pg.example.com")

    def test_keeps_origin_without_path(self):
        from app.services.pasarguard import public_pg_sub_origin

        with patch("app.services.pasarguard._pg", None), patch(
            "app.services.pasarguard.get_settings"
        ) as gs:
            gs.return_value.pg_base_url = "https://pg.example.com:8443"
            self.assertEqual(public_pg_sub_origin(), "https://pg.example.com:8443")

    def test_uses_live_client_base_when_present(self):
        from app.services.pasarguard import public_pg_sub_origin
        from types import SimpleNamespace

        client = SimpleNamespace(base_url="https://live.example.com/dashboard/")
        with patch("app.services.pasarguard._pg", client), patch(
            "app.services.pasarguard.get_settings"
        ) as gs:
            gs.return_value.pg_base_url = "https://ignored.example.com/x"
            self.assertEqual(public_pg_sub_origin(), "https://live.example.com")


class AbsolutizeSubscriptionUrlTests(unittest.TestCase):
    def test_relative_sub_gets_pg_origin(self):
        from app.services.pasarguard import absolutize_subscription_url

        with patch(
            "app.services.pasarguard.public_pg_sub_origin",
            return_value="https://pg.example.com",
        ):
            self.assertEqual(
                absolutize_subscription_url("/sub/abc123"),
                "https://pg.example.com/sub/abc123",
            )

    def test_absolute_https_unchanged(self):
        from app.services.pasarguard import absolutize_subscription_url

        url = "https://sub.cdn.example/sub/tok"
        self.assertEqual(absolutize_subscription_url(url), url)

    def test_relative_without_origin_returns_none(self):
        from app.services.pasarguard import absolutize_subscription_url

        with patch("app.services.pasarguard.public_pg_sub_origin", return_value=""):
            self.assertIsNone(absolutize_subscription_url("/sub/abc"))

    def test_rejects_javascript(self):
        from app.services.pasarguard import absolutize_subscription_url

        self.assertIsNone(absolutize_subscription_url("javascript:alert(1)"))


class UserSubscriptionUrlFallbackTests(unittest.TestCase):
    def test_relative_payload_absolutized(self):
        from app.services.pasarguard import user_subscription_url

        with patch(
            "app.services.pasarguard.public_pg_sub_origin",
            return_value="https://pg.example.com",
        ):
            self.assertEqual(
                user_subscription_url({"subscription_url": "/sub/tok1"}),
                "https://pg.example.com/sub/tok1",
            )

    def test_token_only_uses_origin_not_panel_path(self):
        from app.services.pasarguard import user_subscription_url

        with patch(
            "app.services.pasarguard.public_pg_sub_origin",
            return_value="https://pg.example.com",
        ):
            self.assertEqual(
                user_subscription_url({"subscription_token": "tok2"}),
                "https://pg.example.com/sub/tok2",
            )

    def test_configured_host_url_kept(self):
        from app.services.pasarguard import user_subscription_url

        url = "https://hosts.example.com/sub/keep"
        self.assertEqual(user_subscription_url({"subscription_url": url}), url)


if __name__ == "__main__":
    unittest.main()
