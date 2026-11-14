"""Security hardening: SSRF URL guard, loopback-only setup gate, Host redirect, lockout persistence."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class SafePgUrlTests(unittest.TestCase):
    def test_rejects_metadata_and_userinfo(self):
        from app.services.security_policy import UnsafePgUrlError, assert_safe_pg_base_url

        with self.assertRaises(UnsafePgUrlError):
            assert_safe_pg_base_url("http://169.254.169.254/", resolve_dns=False)
        with self.assertRaises(UnsafePgUrlError):
            assert_safe_pg_base_url("http://metadata.google.internal/", resolve_dns=False)
        with self.assertRaises(UnsafePgUrlError):
            assert_safe_pg_base_url("http://user:pass@evil.example/", resolve_dns=False)

    def test_allows_loopback_and_private_by_default(self):
        from app.services.security_policy import assert_safe_pg_base_url

        self.assertTrue(
            assert_safe_pg_base_url("http://127.0.0.1:8080/api", resolve_dns=False).startswith(
                "http://127.0.0.1:8080"
            )
        )
        self.assertEqual(
            assert_safe_pg_base_url("https://10.0.0.8", resolve_dns=False),
            "https://10.0.0.8",
        )

    def test_public_only_mode_rejects_private(self):
        from app.services.security_policy import UnsafePgUrlError, assert_safe_pg_base_url

        with patch.dict("os.environ", {"PG_URL_PUBLIC_ONLY": "1"}):
            with self.assertRaises(UnsafePgUrlError):
                assert_safe_pg_base_url("http://10.0.0.8", resolve_dns=False)


class SetupGateLoopbackOnlyTests(unittest.TestCase):
    def test_private_lan_requires_gate_token(self):
        from app.services.setup_wizard import is_local_setup_client

        self.assertTrue(is_local_setup_client("127.0.0.1"))
        self.assertTrue(is_local_setup_client("::1"))
        self.assertFalse(is_local_setup_client("10.0.0.5"))
        self.assertFalse(is_local_setup_client("192.168.1.10"))
        self.assertFalse(is_local_setup_client("8.8.8.8"))
        self.assertFalse(is_local_setup_client("169.254.169.254"))


class PanelRedirectHostInjectionTests(unittest.TestCase):
    def test_host_header_not_used_for_absolute_redirect(self):
        from app.api.app import _panel_redirect

        req = MagicMock()
        req.headers = {"host": "evil.example"}
        req.url = MagicMock(netloc="evil.example")

        with patch("app.services.ssl_certs.https_is_active", return_value=False), patch(
            "app.services.ssl_certs.public_panel_base_url", return_value=""
        ):
            resp = _panel_redirect(req, "/home")
        self.assertEqual(resp.headers.get("location"), "/home")
        self.assertNotIn("evil.example", resp.headers.get("location", ""))

    def test_uses_configured_public_base_when_present(self):
        from app.api.app import _panel_redirect

        req = MagicMock()
        req.headers = {"host": "evil.example"}
        with patch("app.services.ssl_certs.https_is_active", return_value=False), patch(
            "app.services.ssl_certs.public_panel_base_url",
            return_value="http://panel.example:9000",
        ):
            resp = _panel_redirect(req, "/home")
        self.assertEqual(resp.headers.get("location"), "http://panel.example:9000/home")


class LoginLockoutPersistenceTests(unittest.TestCase):
    def test_failures_survive_reload(self):
        from app.api import login_guard as lg

        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "login_lockouts.json"
            with patch.object(lg, "_LOGIN_LOCK_FILE", lock), patch.object(
                lg, "DATA_DIR", Path(tmp)
            ):
                lg._LOGIN_FAILURES.clear()
                for _ in range(lg._LOGIN_MAX_FAILURES):
                    lg.login_fail("203.0.113.9")
                self.assertTrue(lg.login_blocked("203.0.113.9"))
                self.assertTrue(lock.is_file())
                data = json.loads(lock.read_text(encoding="utf-8"))
                self.assertIn("203.0.113.9", data)
                # Simulate other worker / process restart: clear memory only.
                # login_blocked must re-read disk (multi-worker share).
                lg._LOGIN_FAILURES.clear()
                self.assertTrue(lg.login_blocked("203.0.113.9"))
                lg.login_success("203.0.113.9")
                self.assertFalse(lg.login_blocked("203.0.113.9"))

    def test_workers_merge_failures_without_clobber(self):
        """Two workers must accumulate failures, not overwrite each other's map."""
        from app.api import login_guard as lg

        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "login_lockouts.json"
            with patch.object(lg, "_LOGIN_LOCK_FILE", lock), patch.object(
                lg, "DATA_DIR", Path(tmp)
            ):
                lg._LOGIN_FAILURES.clear()
                if lock.exists():
                    lock.unlink()
                # Worker A records 5 failures for IP-A
                for _ in range(5):
                    lg.login_fail("198.51.100.1")
                # Simulate worker B with empty memory recording IP-B
                lg._LOGIN_FAILURES.clear()
                for _ in range(5):
                    lg.login_fail("198.51.100.2")
                data = json.loads(lock.read_text(encoding="utf-8"))
                self.assertIn("198.51.100.1", data)
                self.assertIn("198.51.100.2", data)
                lg._LOGIN_FAILURES.clear()
                self.assertEqual(len(data["198.51.100.1"]), 5)
                # Continue failures on A from "empty" worker until blocked
                for _ in range(3):
                    lg.login_fail("198.51.100.1")
                self.assertTrue(lg.login_blocked("198.51.100.1"))


class CardAutoTimestampTests(unittest.TestCase):
    def test_requires_fresh_timestamp(self):
        from app.services.payment_providers.card_auto import parse_card_auto_event

        with self.assertRaises(ValueError):
            parse_card_auto_event(
                {"amount": 1000, "external_ref": "e1", "payment_id": 1}
            )
        now = int(time.time())
        ev = parse_card_auto_event(
            {
                "amount": 1000,
                "external_ref": "e1",
                "payment_id": 1,
                "timestamp": now,
            }
        )
        self.assertEqual(ev.payment_id, 1)
        with self.assertRaises(ValueError):
            parse_card_auto_event(
                {
                    "amount": 1000,
                    "external_ref": "e1",
                    "payment_id": 1,
                    "timestamp": now - 10_000,
                }
            )


class ResellerBotTokenSealTests(unittest.TestCase):
    def test_seal_reveal_and_hash(self):
        from app.services.secret_box import (
            hash_bot_token,
            looks_encrypted_secret,
            reveal_bot_token,
            seal_bot_token,
        )

        token = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
        sealed = seal_bot_token(token)
        self.assertTrue(looks_encrypted_secret(sealed))
        self.assertEqual(reveal_bot_token(sealed), token)
        self.assertEqual(reveal_bot_token(token), token)  # legacy plaintext
        self.assertEqual(len(hash_bot_token(token) or ""), 64)


if __name__ == "__main__":
    unittest.main()
