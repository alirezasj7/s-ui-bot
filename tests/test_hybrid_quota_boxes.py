"""Hybrid Owner: live PG limits as boxes, wallet on dashboard, no false disconnect."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.pasarguard import PasarGuardError


ROOT = Path(__file__).resolve().parents[1]


class LimitSnapshotCardsTests(unittest.TestCase):
    def test_unrestricted_is_empty(self):
        from app.services.pg_quota import limit_snapshot_cards

        self.assertEqual(limit_snapshot_cards({"restricted": False}), [])
        self.assertEqual(limit_snapshot_cards(None), [])

    def test_restricted_rows(self):
        from app.services.pg_quota import limit_snapshot_cards

        cards = limit_snapshot_cards(
            {
                "restricted": True,
                "max_users": 10,
                "current_users": 4,
                "remaining_users": 6,
                "account_data_limit": 50 * (1024**3),
                "account_used_traffic": 5 * (1024**3),
                "account_remaining_traffic": 45 * (1024**3),
                "per_user_data_max": 5 * (1024**3),
                "per_user_expire_max": 30 * 86400,
            }
        )
        labels = [c["label"] for c in cards]
        self.assertIn("سقف کاربران", labels)
        self.assertIn("سقف حجم حساب", labels)
        self.assertIn("حداکثر حجم هر کاربر", labels)
        self.assertIn("حداکثر مدت هر کاربر", labels)
        users = next(c for c in cards if c["key"] == "users")
        self.assertIn("4 از 10", users["value"])


class PgHomeBundlePermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_admins_forbidden_is_still_connected(self):
        from app.services.home_overview import pg_home_bundle

        pg = AsyncMock()
        pg.ensure_token = AsyncMock(return_value="tok")
        pg.get_admins_simple = AsyncMock(side_effect=PasarGuardError("no", 403))
        pg.get_groups_simple = AsyncMock(return_value=[{"id": 1}])
        pg.get_hosts = AsyncMock(side_effect=PasarGuardError("no", 403))
        pg.get_nodes_simple = AsyncMock(side_effect=PasarGuardError("no", 403))
        pg.get_system_stats = AsyncMock(side_effect=PasarGuardError("no", 403))
        with patch("app.services.home_overview.get_pg", return_value=pg):
            summary, nodes = await pg_home_bundle()
        self.assertTrue(summary["ok"])
        self.assertIsNone(summary.get("error"))
        self.assertEqual(summary["groups"], 1)
        self.assertEqual(summary["admins"], 0)
        self.assertEqual(nodes["overall"], "neutral")
        self.assertTrue(nodes["ok"])
        self.assertIsNone(nodes["error"])


class SurfaceContractTests(unittest.TestCase):
    def test_home_shows_wallet_and_limit_board_for_hybrid(self):
        home = (ROOT / "app/web/templates/_home_dash_body.html").read_text(encoding="utf-8")
        ops = (ROOT / "app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        widgets = (ROOT / "app/web/templates/_home_widgets.html").read_text(encoding="utf-8")
        self.assertIn("wallet_card", ops)
        self.assertIn("کیف پول همین حساب", widgets)
        self.assertIn("pg_overview_limit_board", home)
        self.assertNotIn("pg_quota_exhausted_banners", home)

    def test_plans_use_limit_cards_not_warn_flash(self):
        plans = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("pg_snapshot_limit_board", plans)
        self.assertNotIn("سقف زنده این حساب پاسارگارد", plans)
        # Non-owner account-limit boxes on /plans: heading only, no board/box captions.
        self.assertIn("box_captions=false", plans)
        self.assertNotIn("پلن‌ها نباید از محدودیت زنده این نقش بیشتر باشند", plans)
        edit = (ROOT / "app/web/templates/plan_edit.html").read_text(encoding="utf-8")
        self.assertIn("pg_snapshot_limit_board", edit)
        self.assertNotIn("سقف این حساب:", edit)

    def test_setup_hides_probe_and_writes_env_inline(self):
        html = (ROOT / "app/web/templates/setup.html").read_text(encoding="utf-8")
        self.assertIn("setup-audit-limits", html)
        self.assertIn("فایل env را امن نگه دارید", html)
        self.assertIn("progress.hidden = (n >= 4)", html)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".setup-probe[hidden]", css)
        self.assertIn("display: none !important", css.split(".setup-probe[hidden]")[1][:80])


if __name__ == "__main__":
    unittest.main()
