"""Final security audit — admin/reseller cannot bypass PG limits via bot/web.

Scenarios the operator cares about:
1) No nodes permission → no nodes UI on web; no PG ops on reseller bot
2) Admin data pool exhausted / per-user data_limit_max → shop deliver blocked
3) max_users enforced on shop delivery
4) Reseller bot never uses owner PG token for delivery
5) Dual-path invariant: staff XOR reseller
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.authz import authz_from_staff, can_pg_page, can_shop, shop_feature_allowed
from app.services.pg_access import map_pg_role_to_features
from app.services.pg_quota import (
    PgQuotaError,
    assert_admin_can_write,
    assert_can_create_user,
    assert_reseller_can_deliver,
)

ROOT = Path(__file__).resolve().parents[1]
GB = 1024**3


class NodesAclIsolationTests(unittest.TestCase):
    """If PG role has no nodes access, reseller must not see nodes."""

    def test_role_without_nodes_omits_pg_nodes_feature(self):
        role = {
            "permissions": {
                "users": {"read": True, "create": True},
                "nodes": {"read": False, "reconnect": False, "stats": False},
            }
        }
        feats = map_pg_role_to_features(role)
        self.assertNotIn("pg_nodes", feats)
        self.assertIn("pg_users", feats)

    def test_web_can_pg_page_denied_without_pg_nodes(self):
        ctx = authz_from_staff(
            {
                "role": "reseller",
                "permissions": ["dashboard", "plans", "shop_settings"],
                "pg_permissions": ["pg_overview", "pg_users"],
            }
        )
        self.assertFalse(can_pg_page(ctx, "pg_nodes"))
        self.assertTrue(can_pg_page(ctx, "pg_users"))

    def test_reseller_bot_settings_have_no_nodes_surface(self):
        settings = (ROOT / "app/bot/handlers/reseller_settings.py").read_text(encoding="utf-8")
        keyboards = (ROOT / "app/bot/reply_keyboards.py").read_text(encoding="utf-8")
        self.assertNotIn("pg_nodes", settings)
        self.assertNotIn("نودها", settings)
        start = keyboards.find("def _reseller_submenu_entries")
        end = keyboards.find("def reseller_hub_main_keyboard")
        self.assertGreater(start, -1)
        self.assertGreater(end, start)
        hub_fn = keyboards[start:end]
        self.assertNotIn("REPLY_ACTION_PG_NODES", hub_fn)
        self.assertNotIn("نودها", hub_fn)

    def test_open_pg_home_blocks_reseller_bot(self):
        src = (ROOT / "app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        fn = src[src.find("async def open_pg_home") : src.find("async def open_admin_users_hub")]
        self.assertIn("is_reseller_bot", fn)
        self.assertIn("bot_may_open_pg_hub", fn)
        self.assertIn("OWNER_REQUIRED_MESSAGE", fn)
        self.assertNotIn("Role.ADMIN", fn)


class QuotaEnforcementTests(unittest.IsolatedAsyncioTestCase):
    """20GB-style limits must block shop delivery (bot path uses same gate)."""

    async def test_per_user_data_limit_max_blocks_oversized_create(self):
        staff = {"role": "reseller", "pg_admin_username": "shop1", "pg_role_id": 3}
        admin = {
            "username": "shop1",
            "status": "active",
            "users_count": 1,
            "permission_overrides": {},
        }
        role = {
            "id": 3,
            "limits": {"max_users": 50, "data_limit_max": 20 * GB},
            "permissions": {},
        }
        with patch(
            "app.services.pg_quota._load_admin_and_role",
            new=AsyncMock(return_value=(admin, role)),
        ):
            with self.assertRaises(PgQuotaError) as ctx:
                await assert_can_create_user(
                    staff,
                    data_limit=25 * GB,
                    expire_ts=None,
                    from_template=False,
                )
        self.assertIn("حجم", str(ctx.exception))

    async def test_within_20gb_allowed(self):
        staff = {"role": "reseller", "pg_admin_username": "shop1", "pg_role_id": 3}
        admin = {
            "username": "shop1",
            "status": "active",
            "users_count": 1,
            "permission_overrides": {},
        }
        role = {
            "id": 3,
            "limits": {"max_users": 50, "data_limit_max": 20 * GB},
            "permissions": {},
        }
        with patch(
            "app.services.pg_quota._load_admin_and_role",
            new=AsyncMock(return_value=(admin, role)),
        ):
            await assert_can_create_user(
                staff,
                data_limit=10 * GB,
                expire_ts=None,
                from_template=False,
            )

    async def test_exhausted_admin_pool_blocks_write(self):
        admin = {
            "username": "shop1",
            "status": "active",
            "data_limit": 20 * GB,
            "used_traffic": 20 * GB,
        }
        with self.assertRaises(PgQuotaError) as ctx:
            assert_admin_can_write(admin, role={})
        self.assertIn("محدود", str(ctx.exception))

    async def test_max_users_blocks_deliver(self):
        admin = {
            "username": "shop1",
            "status": "active",
            "users_count": 5,
            "permission_overrides": {"max_users": 5},
        }
        role = {"id": 3, "limits": {"max_users": 5}, "permissions": {}}
        with patch(
            "app.services.pg_quota._load_admin_and_role",
            new=AsyncMock(return_value=(admin, role)),
        ):
            with self.assertRaises(PgQuotaError) as ctx:
                await assert_reseller_can_deliver(
                    pg_admin_username="shop1",
                    pg_role_id=3,
                    data_limit=1 * GB,
                    from_template=False,
                )
        self.assertIn("کاربر", str(ctx.exception))

    async def test_missing_pg_link_fail_closed(self):
        with self.assertRaises(PgQuotaError) as ctx:
            await assert_reseller_can_deliver(pg_admin_username=None, data_limit=1 * GB)
        self.assertIn("پاسارگارد", str(ctx.exception))

    async def test_template_path_still_checks_max_users(self):
        admin = {
            "username": "shop1",
            "status": "active",
            "users_count": 2,
            "permission_overrides": {"max_users": 2},
        }
        role = {"id": 3, "limits": {"max_users": 2, "data_limit_max": 5 * GB}, "permissions": {}}
        with patch(
            "app.services.pg_quota._load_admin_and_role",
            new=AsyncMock(return_value=(admin, role)),
        ):
            with self.assertRaises(PgQuotaError):
                await assert_reseller_can_deliver(
                    pg_admin_username="shop1",
                    pg_role_id=3,
                    data_limit=999 * GB,
                    from_template=True,
                )


class ShopAclVsPgAclTests(unittest.TestCase):
    def test_shop_feature_independent_of_pg_nodes(self):
        staff = {
            "role": "reseller",
            "permissions": ["dashboard", "plans", "shop_settings"],
            "pg_permissions": [],
        }
        ctx = authz_from_staff(staff)
        self.assertTrue(can_shop(ctx, "plans"))
        self.assertFalse(can_pg_page(ctx, "pg_nodes"))
        self.assertFalse(can_pg_page(ctx, "pg_users"))
        self.assertFalse(can_shop(ctx, "payments"))
        profile = type(
            "P", (), {"web_permissions": "dashboard,plans,shop_settings", "is_active": True}
        )()
        self.assertTrue(shop_feature_allowed(key="plans", profile=profile))
        self.assertTrue(shop_feature_allowed(key="dashboard", profile=profile))

    def test_pg_staff_has_empty_shop(self):
        ctx = authz_from_staff(
            {
                "role": "pg_staff",
                "permissions": [],
                "pg_permissions": ["pg_overview", "pg_users", "pg_nodes"],
            }
        )
        self.assertFalse(can_shop(ctx, "plans"))
        self.assertTrue(can_pg_page(ctx, "pg_nodes"))


class DeliveryPathWiringTests(unittest.TestCase):
    def test_orders_deliver_uses_reseller_client_and_gate(self):
        src = (ROOT / "app/services/orders.py").read_text(encoding="utf-8")
        self.assertIn("get_pg_for_reseller", src)
        self.assertIn("assert_provision_create", src)
        self.assertIn("assert_provision_renew", src)

    def test_provision_gate_wraps_quota(self):
        src = (ROOT / "app/services/provision_gate.py").read_text(encoding="utf-8")
        self.assertIn("assert_reseller_can_deliver", src)
        self.assertIn("assert_reseller_can_renew", src)

    def test_bot_pg_handlers_platform_admin_only(self):
        src = (ROOT / "app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        self.assertIn("is_platform_admin", src)
        self.assertNotIn("get_pg_for_reseller", src)


class DualPathInvariantTests(unittest.TestCase):
    def test_provision_refuses_existing_staff(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def provision_existing_pg_admin") : src.find(
                "async def convert_staff_to_reseller"
            )
        ]
        self.assertIn("تبدیل خودکار به نماینده مجاز نیست", fn)

    def test_convert_is_explicit_only(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        self.assertIn("async def convert_staff_to_reseller", src)
        pages = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("convert-to-reseller", pages)


class KnownGapDocumentationTests(unittest.TestCase):
    """Document residual risks (not regressions) — keep visible in CI."""

    def test_template_skips_volume_bounds_by_design_comment(self):
        src = (ROOT / "app/services/pg_quota.py").read_text(encoding="utf-8")
        self.assertIn("from_template", src)
        self.assertIn("template create only checks max_users", src)

    def test_shop_create_payload_may_omit_hwid(self):
        orders = (ROOT / "app/services/orders.py").read_text(encoding="utf-8")
        idx = orders.find("pg_user = await pg.create_user(")
        self.assertGreater(idx, 0)
        chunk = orders[idx : idx + 350]
        self.assertIn("build_user_create_payload", chunk)
        self.assertIn("data_limit=data_limit", chunk)
        self.assertNotIn("hwid_limit=", chunk)


if __name__ == "__main__":
    unittest.main()
