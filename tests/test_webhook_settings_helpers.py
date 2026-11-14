"""Helpers for bot webhook / polling settings in the web panel."""

from __future__ import annotations

import unittest

from app.services.setup_wizard import (
    normalize_webhook_base_url,
    normalize_webhook_path,
    resolve_bot_update_mode,
)


class WebhookPathTests(unittest.TestCase):
    def test_default_path(self):
        self.assertEqual(normalize_webhook_path(""), "/telegram/webhook")
        self.assertEqual(normalize_webhook_path(None), "/telegram/webhook")

    def test_adds_slash_and_strips_trail(self):
        self.assertEqual(normalize_webhook_path("hooks/tg/"), "/hooks/tg")
        self.assertEqual(normalize_webhook_path("/telegram/webhook/"), "/telegram/webhook")


class WebhookModeResolveTests(unittest.TestCase):
    def test_polling_clears_url(self):
        mode, base, path = resolve_bot_update_mode(
            mode="polling",
            webhook_url="https://bot.example.com",
            webhook_path="/telegram/webhook",
        )
        self.assertEqual(mode, "polling")
        self.assertEqual(base, "")
        self.assertEqual(path, "/telegram/webhook")

    def test_webhook_requires_https(self):
        with self.assertRaises(ValueError):
            resolve_bot_update_mode(
                mode="webhook",
                webhook_url="http://bot.example.com",
            )

    def test_webhook_falls_back_to_public_base(self):
        mode, base, path = resolve_bot_update_mode(
            mode="webhook",
            webhook_url="",
            public_base_url="https://panel.example.com/",
            webhook_path="telegram/webhook",
        )
        self.assertEqual(mode, "webhook")
        self.assertEqual(base, "https://panel.example.com")
        self.assertEqual(path, "/telegram/webhook")

    def test_normalize_base(self):
        self.assertEqual(
            normalize_webhook_base_url(" https://a.example/ "),
            "https://a.example",
        )


if __name__ == "__main__":
    unittest.main()
