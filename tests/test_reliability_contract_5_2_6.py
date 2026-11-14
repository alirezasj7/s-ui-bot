"""Regression: critical-path reliability (no false disconnect, Jinja dict traps, restore status)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class JinjaDictKeyContract(unittest.TestCase):
    """Dict keys that collide with mapping methods break Jinja dotted access."""

    FORBIDDEN_TEMPLATE_ATTRS = (
        # action center / similar: never iterate ac.items (dict.items method)
        "ac.items",
        "action_center.items",
    )

    def test_home_templates_use_entries_not_items(self):
        for name in ("home.html", "reseller_home.html", "inbox.html"):
            tpl = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
            self.assertNotIn("ac.items", tpl, msg=name)
        inbox = (ROOT / "app/web/templates/inbox.html").read_text(encoding="utf-8")
        self.assertIn("ac.entries", inbox)

    def test_action_center_payload_key_is_entries(self):
        src = (ROOT / "app/services/ux20.py").read_text(encoding="utf-8")
        self.assertIn('"entries": items', src)
        self.assertIn("Key must NOT be named ``items``", src)

    def test_empty_action_center_uses_entries(self):
        src = (ROOT / "app/services/panel_inbox.py").read_text(encoding="utf-8")
        self.assertIn('_EMPTY_ACTION = {"entries": [], "has_items": False}', src)
        self.assertNotIn('"items": []', src)


class HomeDegradedNoFakeDisconnect(unittest.TestCase):
    def test_degraded_shell_uses_unchecked_not_fake_cut(self):
        src = (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("_UNCHECKED_CONN", src)
        self.assertIn("dashboard_degraded", src)
        self.assertIn("unchecked", src)
        # Old band-aid that painted Bot/PG as قطع
        self.assertNotIn('"error": "بارگذاری ناقص"', src)
        # Body fragment / full page render stays outside data try (diagnosable 500s).
        self.assertIn("_render_home_result", src)
        self.assertIn("home_dashboard_body", src)

    def test_templates_handle_unchecked_conn(self):
        # Markup lives in dash body partials (home.html only includes them).
        for name in ("_home_dash_body.html", "_reseller_home_dash_body.html"):
            tpl = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
            self.assertIn("unchecked", tpl, msg=name)
            self.assertIn("dashboard_degraded", tpl, msg=name)
            self.assertIn("بررسی نشده", tpl, msg=name)


class RestoreStatusContract(unittest.TestCase):
    def test_restore_has_restart_required_and_clear(self):
        src = (ROOT / "app/services/backup.py").read_text(encoding="utf-8")
        self.assertIn("restart_required", src)
        self.assertIn("clear_idle_restore_status", src)
        self.assertIn("_STATUS_LOCK", src)
        self.assertIn("_replace_restore_status", src)

    def test_api_progressive_enhancement(self):
        src = (ROOT / "app/api/backup_pages.py").read_text(encoding="utf-8")
        self.assertIn("_wants_json", src)
        self.assertIn("/backup/clear", src)
        self.assertIn("restore=1", src)

    def test_settings_resolves_stale_and_clears_on_ok(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("resolve_stale_restore_status", src)
        self.assertIn("clear_idle_restore_status", src)

    def test_validate_failure_finishes_status(self):
        """Early validate failure must not leave state=running forever."""
        from app.services import backup as backup_mod

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            status_file = data / "backup_restore.json"
            with mock.patch.object(backup_mod, "DATA_DIR", data), mock.patch.object(
                backup_mod, "RESTORE_STATUS_FILE", status_file
            ), mock.patch.object(backup_mod, "BACKUP_DIR", data / "backups"):
                (data / "backups").mkdir()
                # Seed running as async start would
                backup_mod._replace_restore_status(
                    {
                        "state": "running",
                        "message": "شروع ریستور…",
                        "started_at": backup_mod._now_iso(),
                    }
                )
                bad = data / "backups" / "nope.zip"
                bad.write_bytes(b"not-a-zip")
                result = backup_mod.restore_backup(bad, restart=False, safety_backup=False)
                self.assertFalse(result.get("ok"))
                st = backup_mod.read_restore_status()
                self.assertEqual(st.get("state"), "error", msg=st)
                self.assertNotEqual(st.get("state"), "running")

    def test_awaiting_blocks_second_start(self):
        from app.runtime import BOOT_ID
        from app.services import backup as backup_mod

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            status_file = data / "backup_restore.json"
            with mock.patch.object(backup_mod, "DATA_DIR", data), mock.patch.object(
                backup_mod, "RESTORE_STATUS_FILE", status_file
            ), mock.patch.object(backup_mod, "BACKUP_DIR", data / "backups"), mock.patch.object(
                backup_mod, "_RESTORE_THREAD", None
            ):
                (data / "backups").mkdir()
                # Same boot id → restart has not happened yet; block a second start.
                backup_mod._replace_restore_status(
                    {
                        "state": "done",
                        "awaiting_restart": True,
                        "message": "awaiting",
                        "finished_at": backup_mod._now_iso(),
                        "pre_boot_id": BOOT_ID,
                    }
                )
                zip_path = data / "backups" / "x.zip"
                zip_path.write_bytes(b"x" * 100)
                out = backup_mod.start_restore_async(zip_path, restart=False, safety_backup=False)
                self.assertFalse(out.get("ok"))
                self.assertIn("راه‌اندازی مجدد", out.get("error") or "")


if __name__ == "__main__":
    unittest.main()
