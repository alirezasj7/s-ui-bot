"""Tests for panel update status recovery and GitHub version checks."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services import panel_update as pu
from app.services.updates import clear_update_cache, is_newer, is_same_or_newer, peek_update_cache


class VersionCompareTests(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(is_newer("1.7.35", "1.7.34"))
        self.assertFalse(is_newer("1.7.34", "1.7.34"))
        self.assertFalse(is_newer("1.7.33", "1.7.34"))

    def test_same_or_newer(self):
        self.assertTrue(is_same_or_newer("1.7.34", "1.7.34"))
        self.assertTrue(is_same_or_newer("1.7.35", "1.7.34"))
        self.assertFalse(is_same_or_newer("1.7.33", "1.7.34"))


class PanelUpdatePathEnvTests(unittest.TestCase):
    def test_env_with_path_includes_system_bins(self):
        env = pu._env_with_path()
        self.assertIn("/usr/bin", env.get("PATH", ""))
        self.assertEqual(env.get("GIT_TERMINAL_PROMPT"), "0")

    def test_run_works_with_short_path(self):
        import os
        import sys

        with patch.dict(os.environ, {"PATH": "/nonexistent"}, clear=False):
            code, out = pu._run([sys.executable, "-c", "print('ok')"], timeout=10)
        self.assertEqual(code, 0)
        self.assertIn("ok", out)


class NoVersionRollbackTests(unittest.TestCase):
    def test_update_service_exposes_no_rollback_or_snapshot_entry_points(self):
        for name in ("start_rollback", "start_rollback_to_version", "create_snapshot", "list_snapshots", "get_snapshot"):
            self.assertFalse(hasattr(pu, name), name)

    def test_update_page_context_carries_no_rollback_data(self):
        context = pu._degraded_update_page_context()
        for key in ("rollback_versions", "can_rollback", "snapshots"):
            self.assertNotIn(key, context)

    def test_default_status_has_no_mode_or_snapshot(self):
        status = pu._default_status()
        self.assertNotIn("mode", status)
        self.assertNotIn("snapshot_id", status)


class StaleUpdateStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.status = Path(self.tmp.name) / "panel_update.json"
        self.patches = [
            patch.object(pu, "STATUS_FILE", self.status),
            patch.object(pu, "DATA_DIR", Path(self.tmp.name)),
            patch.object(pu, "local_version", return_value="1.7.35"),
            patch.object(pu, "_THREAD", None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _write(self, data: dict):
        self.status.write_text(json.dumps(data), encoding="utf-8")

    def _iso_ago(self, seconds: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

    def test_clear_idle_wipes_awaiting(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "1.7.30",
                "log": ["x"],
                "step_key": "restart",
            }
        )
        out = pu.clear_idle_status()
        self.assertEqual(out["state"], "idle")
        self.assertFalse(out.get("awaiting_restart"))

    def test_resolve_clears_when_boot_changed_and_version_ok(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "1.7.35",
                "pre_boot_id": "old-boot",
                "finished_at": self._iso_ago(5),
                "log": ["waiting"],
                "step_key": "restart",
            }
        )
        with patch("app.runtime.BOOT_ID", "new-boot"):
            out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "idle")
        self.assertFalse(out.get("awaiting_restart"))

    def test_resolve_keeps_awaiting_same_boot_even_if_version_matches(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "mode": "update",
                "to_version": "1.7.35",
                "pre_boot_id": "same-boot",
                "finished_at": self._iso_ago(5),
                "log": ["waiting"],
                "step_key": "restart",
            }
        )
        with patch("app.runtime.BOOT_ID", "same-boot"):
            out = pu.resolve_stale_update_status()
        self.assertTrue(out.get("awaiting_restart"))

    def test_status_file_left_by_an_older_rollback_still_resolves(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "mode": "rollback",
                "snapshot_id": "abc123",
                "to_version": "1.7.35",
                "pre_boot_id": "old-boot",
                "finished_at": self._iso_ago(5),
                "log": ["waiting"],
                "step_key": "restart",
            }
        )
        with patch("app.runtime.BOOT_ID", "new-boot"):
            out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "idle")
        self.assertFalse(out.get("awaiting_restart"))

    def test_resolve_times_out_awaiting(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "9.9.9",
                "pre_boot_id": "old",
                "finished_at": self._iso_ago(pu.AWAITING_RESTART_TIMEOUT_SEC + 10),
                "step_key": "restart",
            }
        )
        with patch("app.runtime.BOOT_ID", "old"):
            out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "error")
        self.assertFalse(out.get("awaiting_restart"))
        self.assertTrue(out.get("restart_required"))

    def test_zombie_running_becomes_error(self):
        self._write(
            {
                "state": "running",
                "started_at": self._iso_ago(120),
                "step_key": "pull",
                "awaiting_restart": False,
            }
        )
        out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "error")
        self.assertIn("ناتمام", out.get("error") or "")

    def test_restart_required_kept(self):
        self._write(
            {
                "state": "error",
                "restart_required": True,
                "awaiting_restart": False,
                "message": "manual restart",
                "error": "manual restart",
            }
        )
        out = pu.resolve_stale_update_status()
        self.assertTrue(out.get("restart_required"))
        self.assertEqual(out["state"], "error")

    def test_legacy_awaiting_clears_after_grace_when_version_reached(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "1.7.30",
                "pre_boot_id": None,
                "finished_at": self._iso_ago(30),
                "log": ["old"],
                "step_key": "restart",
            }
        )
        out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "idle")


class UpdateCachePeekTests(unittest.TestCase):
    def test_peek_none_by_default(self):
        clear_update_cache()
        self.assertIsNone(peek_update_cache())


if __name__ == "__main__":
    unittest.main()
