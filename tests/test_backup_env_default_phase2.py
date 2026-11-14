"""Phase 2 — backup defaults exclude .env; with-env needs explicit confirm."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class CreateBackupDefaultTests(unittest.TestCase):
    def test_create_backup_default_excludes_env(self):
        from app.services import backup as backup_mod

        sig = inspect.signature(backup_mod.create_backup)
        self.assertFalse(sig.parameters["include_env"].default)

    def test_safety_restore_still_passes_include_env_true(self):
        src = Path("app/services/backup.py").read_text(encoding="utf-8")
        # Pre-restore safety archive must keep secrets for rollback.
        self.assertIn("include_env=True", src)
        self.assertIn("safety", src.lower())

    def test_baseline_still_includes_env(self):
        src = Path("app/services/baseline.py").read_text(encoding="utf-8")
        self.assertIn("include_env=True", src)


class WebBackupConfirmTests(unittest.TestCase):
    def test_backup_create_route_requires_confirm_for_env(self):
        src = Path("app/api/backup_pages.py").read_text(encoding="utf-8")
        self.assertIn("confirm_include_env", src)
        self.assertIn("want_env and not confirmed", src)
        self.assertIn("تأیید امنیتی", src)

    def test_template_default_unchecked_and_second_confirm(self):
        tpl = Path("app/web/templates/_settings_backup.html").read_text(encoding="utf-8")
        self.assertIn('id="backup-include-env"', tpl)
        self.assertNotIn(
            'name="include_env" value="1" checked',
            tpl,
        )
        self.assertIn("confirm_include_env", tpl)
        self.assertIn("هشدار امنیتی", tpl)
        self.assertIn("web_admin.json", tpl)
        self.assertIn("backup-env-confirm-wrap", tpl)


class BotBackupConfirmTests(unittest.TestCase):
    def test_reply_keyboard_default_is_safe(self):
        from app.bot.reply_keyboards import _admin_backup_submenu_entries

        entries = dict(_admin_backup_submenu_entries())
        self.assertEqual(entries["backup_create"], "🆕 ساخت بکاپ")
        self.assertIn("backup_create_env", entries)
        self.assertNotIn("backup_create_noenv", entries)

    def test_reply_nav_maps_create_to_noenv(self):
        src = Path("app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        # Primary backup_create action must hit :noenv
        block_start = src.index('elif action == "backup_create":')
        block_end = src.index('elif action == "backup_create_env":', block_start)
        block = src[block_start:block_end]
        self.assertIn("adm:backup:create:noenv", block)
        self.assertNotIn("adm:backup:create:env", block)

    def test_env_create_has_confirm_handler(self):
        src = Path("app/bot/handlers/admin_backup.py").read_text(encoding="utf-8")
        self.assertIn("backup_create_env_ask", src)
        self.assertIn("adm:backup:create:env:yes", src)
        self.assertIn("تأیید بکاپ با .env", src)
        # Default create path must not treat bare create as include_env
        self.assertIn('include_env = data.endswith(":env:yes")', src)

    def test_hub_text_says_default_without_env(self):
        from app.bot.handlers.admin_backup import _hub_text

        text = _hub_text([])
        self.assertIn("بدون", text)
        self.assertIn(".env", text)


class ResellerBackupAclLockTests(unittest.TestCase):
    def test_backup_handlers_require_owner(self):
        src = Path("app/bot/handlers/admin_backup.py").read_text(encoding="utf-8")
        # Every mutating backup callback must be owner-gated (decorator below filter).
        for marker in (
            'F.data == "adm:backup"',
            'F.data == "adm:backup:create:env"',
            'F.data.startswith("adm:backup:create")',
            'F.data.startswith("adm:backup:item:")',
            'F.data.startswith("adm:backup:dl:")',
            'F.data.startswith("adm:backup:del:")',
            'F.data.startswith("adm:backup:restore:")',
            'F.data == "adm:backup:upload"',
        ):
            self.assertIn(marker, src)
            idx = src.index(marker)
            window = src[idx : idx + 200]
            self.assertIn(
                "@require_bot_owner_handler",
                window,
                msg=f"missing owner gate near {marker}",
            )

    def test_web_backup_routes_require_admin(self):
        src = Path("app/api/backup_pages.py").read_text(encoding="utf-8")
        self.assertIn("Depends(require_admin)", src)
        # create/download/delete/restore all use require_admin
        self.assertGreaterEqual(src.count("Depends(require_admin)"), 4)

    def test_reseller_bot_cannot_map_backup_labels(self):
        from app.bot.reply_keyboards import reply_action_map

        ui = {"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت"}
        mapping = reply_action_map(
            "admin", ui=ui, include_submenus=True, is_reseller_bot=True
        )
        self.assertNotIn("🆕 ساخت بکاپ", mapping)
        self.assertNotIn("🆕 بکاپ + .env", mapping)
        self.assertNotIn("💾 بکاپ / ریستور", mapping)


class CliBackupDefaultTests(unittest.TestCase):
    def test_cli_default_excludes_env(self):
        src = Path("app/cli/main.py").read_text(encoding="utf-8")
        self.assertIn("--with-env", src)
        self.assertIn("include_env=bool(args.with_env)", src)


if __name__ == "__main__":
    unittest.main()
