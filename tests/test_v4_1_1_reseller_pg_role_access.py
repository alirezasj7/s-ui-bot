"""v4.1.1 — limited PG role self-access, role sync, auto-approve, UI polish."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class TestLimitedRoleOverview(unittest.IsolatedAsyncioTestCase):
    async def test_overview_uses_own_client_without_owner_get_pg(self):
        from app.services.pg_overview import build_reseller_pg_overview

        own = {
            "username": "limited_res",
            "total_users": 2,
            "used_traffic": 1024,
            "status": "active",
            "role": {"id": 9, "name": "limited", "permissions": {"users": {"read": True}}},
        }
        staff_pg = MagicMock()
        staff_pg.get_admin = AsyncMock(return_value=own)
        staff_pg.get_users = AsyncMock(return_value={"users": []})
        staff_pg.get_admin_role = AsyncMock(return_value=own["role"])

        with (
            patch(
                "app.services.pg_read.get_pg_for_reseller",
                new=AsyncMock(return_value=staff_pg),
            ),
            patch(
                "app.services.pg_overview.get_pg",
                side_effect=AssertionError("L1/L2 must not use Owner get_pg()"),
            ),
            patch(
                "app.services.pg_read.fetch_own_admin_meta",
                side_effect=AssertionError("L1/L2 must not use Owner admin meta"),
            ),
        ):
            out = await build_reseller_pg_overview(
                {
                    "pg_admin_username": "limited_res",
                    "role": "reseller",
                    "bot_user_id": 7,
                    "pg_role_id": 9,
                },
                session=MagicMock(),
            )
        self.assertTrue(out["ready"], out.get("error"))
        self.assertIsNone(out.get("error"))
        self.assertEqual(out["users"]["used"], 2)

    async def test_overview_fail_closed_when_own_admin_unavailable(self):
        from app.services.pg_overview import build_reseller_pg_overview

        staff_pg = MagicMock()
        staff_pg.get_admin = AsyncMock(return_value=None)
        staff_pg.get_users = AsyncMock(return_value={"users": []})

        with (
            patch(
                "app.services.pg_read.get_pg_for_reseller",
                new=AsyncMock(return_value=staff_pg),
            ),
            patch(
                "app.services.pg_overview.get_pg",
                side_effect=AssertionError("L1/L2 must not use Owner get_pg()"),
            ),
        ):
            out = await build_reseller_pg_overview(
                {
                    "pg_admin_username": "limited_res",
                    "role": "reseller",
                    "bot_user_id": 7,
                    "pg_role_id": 9,
                },
                session=MagicMock(),
            )
        self.assertFalse(out["ready"])
        self.assertIsNotNone(out.get("error"))

    async def test_fetch_own_admin_meta_rejects_mismatch(self):
        from app.services.pg_read import fetch_own_admin_meta

        pg = MagicMock()
        pg.get_admin = AsyncMock(
            return_value={"username": "other_admin", "id": 1}
        )
        with patch("app.services.pg_read.get_pg", return_value=pg):
            self.assertIsNone(await fetch_own_admin_meta("limited_res"))


class TestMapPgRoleOverview(unittest.TestCase):
    def test_users_read_implies_overview(self):
        from app.services.pg_access import map_pg_role_to_features

        feats = map_pg_role_to_features(
            {
                "is_owner": False,
                "permissions": {"users": {"read": True}},
            }
        )
        self.assertIn("pg_overview", feats)
        self.assertIn("pg_users", feats)


class TestRoleEditSync(unittest.TestCase):
    def test_reseller_edit_save_pushes_role_to_pg(self):
        src = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
        chunk = src.split("async def reseller_edit_save", 1)[1].split(
            "async def reseller_billing_topup", 1
        )[0]
        self.assertIn('modify_admin', chunk)
        self.assertIn('"role_id"', chunk)


class TestAutoApproveAfterPayment(unittest.TestCase):
    def test_mark_paid_calls_approve(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        chunk = src.split("async def mark_application_paid", 1)[1].split(
            "async def provision_reseller", 1
        )[0]
        self.assertIn("approve_application", chunk)
        self.assertIn("_reseller_app_creds", chunk)

    def test_notify_loads_reseller_plan_for_app_orders(self):
        src = (ROOT / "app/services/notifications.py").read_text(encoding="utf-8")
        chunk = src.split('if note.startswith("reseller_app:")', 1)[1].split(
            'if note.startswith("renew:")', 1
        )[0]
        self.assertIn("ResellerPlan", chunk)
        self.assertIn("format_reseller_plan_apply_detail", chunk)


class TestUiPolish(unittest.TestCase):
    def test_plans_no_duplicate_flash(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        # Page-level flash must stay in base.html only. Category create/edit
        # flash is scoped inside the modal (settings-modal-flash).
        self.assertNotIn(
            '{% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}',
            html.split("modal-plan-categories", 1)[0],
        )
        self.assertIn("settings-modal-flash", html)
        self.assertIn("open_categories and (flash_ok or flash_err)", html)
        base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("_catalog_modal_open", base)
        self.assertIn("open_categories", base)

    def test_control_bg_css_var(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("--control-bg:", css)
        self.assertIn("background: var(--control-bg)", css)
        self.assertIn("background-color: var(--control-bg)", css)

    def test_panel_js_clears_form_err_on_close(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("form_err", js)
        self.assertIn("form-err", js)


class TestGetAdminDirectPath(unittest.TestCase):
    def test_get_admin_tries_by_username_first(self):
        src = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        chunk = src.split("async def get_admin", 1)[1].split("async def get_admin_roles", 1)[0]
        # Skip docstring — compare request path order in the body
        body = chunk.split('"""', 2)[-1] if chunk.count('"""') >= 2 else chunk
        self.assertIn("/api/admin/by-username/", body)
        idx_direct = body.find("/api/admin/by-username/")
        idx_list = body.find('"/api/admins"')
        self.assertGreaterEqual(idx_direct, 0)
        self.assertGreaterEqual(idx_list, 0)
        self.assertLess(idx_direct, idx_list)
        # Own-account lookup must run before directory paths so limited
        # roles (no admins.read) can still resolve themselves.
        src_gate = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        self.assertIn('self.request("GET", "/api/admin")', src_gate)
        idx_self = src_gate.find('self.request("GET", "/api/admin")')
        idx_by_name = src_gate.find("/api/admin/by-username/")
        self.assertLess(idx_self, idx_by_name)


if __name__ == "__main__":
    unittest.main()
