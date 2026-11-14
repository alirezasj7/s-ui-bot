"""Tests for automatic panel restart after updates."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest import mock


class RestartFallbackTests(unittest.TestCase):
    def test_restart_prefers_self_restart_without_sudo(self):
        from app.services import service_control as sc

        with mock.patch.object(sc, "ensure_restart_helper", return_value=(False, "no sudo")):
            with mock.patch.object(sc, "_sudo_restart_works", return_value=False):
                with mock.patch.object(sc, "can_passwordless_sudo", return_value=False):
                    with mock.patch.object(sc, "under_systemd_service", return_value=True):
                        with mock.patch.object(
                            sc, "_schedule_self_restart", return_value=(True, "systemd")
                        ) as m:
                            with sc._restart_lock:
                                sc._restart_scheduled = False
                            ok, note = sc.restart_panel_service(reason="test", delay_sec=1.0)
                            self.assertTrue(ok)
                            self.assertIn("systemd", note)
                            m.assert_called_once()

    def test_panel_update_spawns_restart_script(self):
        src = Path("app/services/panel_update.py").read_text(encoding="utf-8")
        self.assertIn("panel_restart.py", src)
        self.assertIn("importlib.reload", src)
        self.assertTrue(Path("scripts/panel_restart.py").is_file())

    def test_schedule_signature(self):
        from app.services.service_control import schedule_panel_restart

        sig = inspect.signature(schedule_panel_restart)
        self.assertIn("delay_sec", sig.parameters)


if __name__ == "__main__":
    unittest.main()
