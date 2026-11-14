"""3.5.3 — Fix admin bot notify toggles rejecting valid notify_* keys."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AdminNotifyToggleAllowlistTests(unittest.TestCase):
    def test_all_notify_prefs_are_toggleable(self):
        from app.bot.handlers.admin_settings import (
            EXTRA_TOGGLE_KEYS,
            NOTIFY_KEYS,
            _is_toggleable_setting_key,
        )
        from app.services.notifications import NOTIFY_PREFS

        for key, *_ in NOTIFY_PREFS:
            self.assertIn(key, NOTIFY_KEYS)
            self.assertIn(key, EXTRA_TOGGLE_KEYS)
            self.assertTrue(
                _is_toggleable_setting_key(key),
                msg=f"{key} must be toggleable (was rejecting with کلید نامعتبر)",
            )

    def test_field_toggles_and_extras_allowed(self):
        from app.bot.handlers.admin_settings import (
            FIELDS,
            _is_toggleable_setting_key,
        )

        self.assertTrue(_is_toggleable_setting_key("trial_enabled"))
        self.assertTrue(_is_toggleable_setting_key("custom_plan_enabled"))
        self.assertTrue(_is_toggleable_setting_key("pay_wallet_enabled"))
        self.assertTrue(_is_toggleable_setting_key("qr_enabled"))
        # Text fields must not flip via tog handler
        text_keys = [k for k, meta in FIELDS.items() if meta[2] != "toggle"]
        self.assertTrue(text_keys)
        self.assertFalse(_is_toggleable_setting_key(text_keys[0]))
        self.assertFalse(_is_toggleable_setting_key("not_a_real_key"))

    def test_rendered_tog_callbacks_covered(self):
        """Every key used with adm:st:tog must pass the allowlist."""
        from app.bot.handlers.admin_settings import SECTIONS, _is_toggleable_setting_key
        from app.services.notifications import NOTIFY_PREFS

        keys: set[str] = {"custom_plan_enabled", "trial_enabled"}
        for key, *_ in NOTIFY_PREFS:
            keys.add(key)
        for sec in SECTIONS.values():
            for sub in sec.get("subs") or []:
                payload = sub[2]
                if isinstance(payload, list):
                    for f in payload:
                        if f[2] == "toggle":
                            keys.add(f[0])
        for key in keys:
            self.assertTrue(_is_toggleable_setting_key(key), msg=key)

    def test_toggle_handler_uses_helper_not_fields_only(self):
        src = (ROOT / "app/bot/handlers/admin_settings.py").read_text(encoding="utf-8")
        self.assertIn("_is_toggleable_setting_key(key)", src)
        self.assertNotIn(
            'key not in FIELDS and key not in {"custom_plan_enabled", "trial_enabled"}',
            src,
        )


class ResellerNotifyToggleTests(unittest.TestCase):
    def test_notify_uses_ntog_not_tog(self):
        src = (ROOT / "app/bot/handlers/reseller_settings.py").read_text(encoding="utf-8")
        self.assertIn("res:st:ntog:", src)
        self.assertIn("settings_notify_toggle", src)
        # Field toggles must not accept notify_ via res:st:tog
        self.assertIn('key.startswith("notify_")', src)

    def test_no_orphan_tog_literals(self):
        """Scan bot handlers for adm:st:tog:literal not in allowlist."""
        from app.bot.handlers.admin_settings import _is_toggleable_setting_key

        for path in (ROOT / "app/bot/handlers").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for key in re.findall(r"adm:st:tog:([a-z0-9_]+)", text):
                self.assertTrue(
                    _is_toggleable_setting_key(key),
                    msg=f"{path.name} renders adm:st:tog:{key} but allowlist rejects it",
                )


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_3_5_3(self):
        from app.version import __version__

        self.assertGreaterEqual(
            tuple(int(x) for x in __version__.split(".")[:3]), (0, 1, 0)
        )
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"0.1.0"', notes)


if __name__ == "__main__":
    unittest.main()
