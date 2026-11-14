"""Fail-closed shop tenant isolation — resellers must never see platform data."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.plans_catalog import (
    apply_catalog_owner_filter,
    catalog_owner_id,
    plan_belongs_to_staff,
    require_catalog_owner_id,
)
from app.services.shop_scope import (
    ShopScopeError,
    assert_order_in_scope,
    empty_shop_stats,
    is_platform_admin,
    require_shop_owner_id,
    shop_owner_id,
)


class ShopOwnerIdTests(unittest.TestCase):
    def _owner(self, **extra):
        staff = {
            "role": "admin",
            "org_principal_id": 1,
            "org_depth": 0,
            "org_parent_id": None,
            "org_status": "active",
            "bot_user_id": 99,
        }
        staff.update(extra)
        return staff

    def test_admin_has_no_shop_id(self):
        # Bare role=admin is not platform; explicit Owner has None shop id.
        self.assertIsNone(shop_owner_id({"role": "admin", "bot_user_id": 99}))
        self.assertFalse(is_platform_admin({"role": "admin"}))
        self.assertIsNone(shop_owner_id(self._owner()))
        self.assertTrue(is_platform_admin(self._owner()))

    def test_reseller_with_id(self):
        self.assertEqual(shop_owner_id({"role": "reseller", "bot_user_id": 42}), 42)

    def test_reseller_without_id_is_none(self):
        self.assertIsNone(shop_owner_id({"role": "reseller"}))
        self.assertIsNone(shop_owner_id({"role": "reseller", "bot_user_id": 0}))
        self.assertIsNone(shop_owner_id({"role": "reseller", "bot_user_id": "x"}))

    def test_pg_staff_never_gets_platform_scope(self):
        self.assertIsNone(shop_owner_id({"role": "pg_staff", "bot_user_id": 1}))
        self.assertIsNone(shop_owner_id({"role": "pg_staff"}))

    def test_require_shop_owner_fails_closed(self):
        with self.assertRaises(ShopScopeError):
            require_shop_owner_id({"role": "pg_staff"})
        with self.assertRaises(ShopScopeError):
            require_shop_owner_id({"role": "reseller"})
        with self.assertRaises(ShopScopeError):
            require_shop_owner_id({"role": "admin"})
        with self.assertRaises(ShopScopeError):
            require_shop_owner_id(self._owner())
        self.assertEqual(require_shop_owner_id({"role": "reseller", "bot_user_id": 7}), 7)

    def test_assert_order_in_scope(self):
        order = SimpleNamespace(reseller_id=7)
        assert_order_in_scope(self._owner(), order)
        assert_order_in_scope({"role": "reseller", "bot_user_id": 7}, order)
        with self.assertRaises(ShopScopeError):
            assert_order_in_scope({"role": "reseller", "bot_user_id": 8}, order)
        with self.assertRaises(ShopScopeError):
            assert_order_in_scope({"role": "pg_staff"}, order)
        with self.assertRaises(ShopScopeError):
            # Bare admin is not platform — deny
            assert_order_in_scope({"role": "admin"}, order)
        with self.assertRaises(ShopScopeError):
            # NULL reseller_id is platform/admin shop — never match missing staff scope
            assert_order_in_scope(
                {"role": "reseller", "bot_user_id": None},
                SimpleNamespace(reseller_id=None),
            )

    def test_empty_stats_zeros(self):
        s = empty_shop_stats()
        self.assertEqual(s["users"], 0)
        self.assertEqual(s["orders"], 0)
        self.assertEqual(s["revenue"], 0)


class CatalogIsolationTests(unittest.TestCase):
    def _owner(self):
        return {
            "role": "admin",
            "org_principal_id": 1,
            "org_depth": 0,
            "org_parent_id": None,
            "org_status": "active",
        }

    def test_catalog_owner_id(self):
        self.assertIsNone(catalog_owner_id(self._owner()))
        self.assertIsNone(catalog_owner_id({"role": "admin"}))  # bare → no platform
        self.assertEqual(catalog_owner_id({"role": "reseller", "bot_user_id": 3}), 3)
        self.assertIsNone(catalog_owner_id({"role": "pg_staff"}))
        self.assertIsNone(catalog_owner_id({"role": "reseller", "bot_user_id": 0}))

    def test_require_catalog_write(self):
        self.assertIsNone(require_catalog_owner_id(self._owner()))
        self.assertEqual(require_catalog_owner_id({"role": "reseller", "bot_user_id": 9}), 9)
        with self.assertRaises(ShopScopeError):
            require_catalog_owner_id({"role": "pg_staff"})
        with self.assertRaises(ShopScopeError):
            require_catalog_owner_id({"role": "reseller"})
        with self.assertRaises(ShopScopeError):
            require_catalog_owner_id({"role": "admin"})

    def test_filter_fails_closed_for_pg_staff(self):
        q = MagicMock()
        q.where = MagicMock(return_value="filtered")
        out = apply_catalog_owner_filter(q, {"role": "pg_staff"})
        self.assertEqual(out, "filtered")
        # Must use impossible id predicate, not platform owner_reseller_id IS NULL
        args, _kwargs = q.where.call_args
        expr = args[0]
        self.assertIn("plans.id", str(expr).lower().replace('"', ""))

    def test_filter_reseller_scoped(self):
        q = MagicMock()
        q.where = MagicMock(return_value="ok")
        apply_catalog_owner_filter(q, {"role": "reseller", "bot_user_id": 5})
        expr = str(q.where.call_args[0][0]).lower()
        self.assertIn("owner_reseller_id", expr)

    def test_filter_admin_platform_only(self):
        q = MagicMock()
        q.where = MagicMock(return_value="ok")
        apply_catalog_owner_filter(q, self._owner())
        expr = str(q.where.call_args[0][0]).lower()
        self.assertIn("owner_reseller_id", expr)
        self.assertIn("is null", expr)

    def test_bare_admin_catalog_not_platform(self):
        q = MagicMock()
        q.where = MagicMock(return_value="empty")
        apply_catalog_owner_filter(q, {"role": "admin"})
        # Fail closed — not platform IS NULL filter
        expr = str(q.where.call_args[0][0]).lower().replace('"', "")
        self.assertIn("plans.id", expr)

    def test_plan_belongs_to_staff(self):
        platform = SimpleNamespace(owner_reseller_id=None)
        shop = SimpleNamespace(owner_reseller_id=5)
        self.assertTrue(plan_belongs_to_staff(platform, self._owner()))
        self.assertFalse(plan_belongs_to_staff(shop, self._owner()))
        self.assertFalse(plan_belongs_to_staff(platform, {"role": "admin"}))
        self.assertTrue(plan_belongs_to_staff(shop, {"role": "reseller", "bot_user_id": 5}))
        self.assertFalse(plan_belongs_to_staff(platform, {"role": "reseller", "bot_user_id": 5}))
        self.assertFalse(plan_belongs_to_staff(platform, {"role": "pg_staff"}))
        self.assertFalse(plan_belongs_to_staff(shop, {"role": "pg_staff"}))
        self.assertFalse(plan_belongs_to_staff(platform, {"role": "reseller"}))


class SourceGuardTests(unittest.TestCase):
    """Static guards against regressing to unscoped dashboard queries."""

    def test_dashboard_uses_shop_scope(self):
        from pathlib import Path

        # The bot overview moved out of app.py; guard both files.
        src = Path("app/api/app.py").read_text(encoding="utf-8") + Path(
            "app/services/bot_overview.py"
        ).read_text(encoding="utf-8")
        # Old leak pattern must stay gone
        self.assertNotIn(
            'rid = staff.get("bot_user_id") if staff.get("role") == "reseller" else None',
            src,
        )
        self.assertIn("empty_shop_stats", src)
        self.assertIn("shop_owner_id", src)
        # Orders must not use nullable bot_user_id equality (IS NULL → admin rows)
        self.assertNotIn(
            'Order.reseller_id == staff.get("bot_user_id")',
            src,
        )

    def test_shop_scope_module_exists(self):
        from pathlib import Path

        self.assertTrue(Path("app/services/shop_scope.py").is_file())

    def test_check_bot_connection_has_no_platform_fallback(self):
        from pathlib import Path

        src = Path("app/services/home_overview.py").read_text(encoding="utf-8")
        # Silent fallback leaked main admin bot status to reseller dashboards
        self.assertNotIn(
            'token or current_setup_values().get("BOT_TOKEN")',
            src,
        )
        self.assertIn("Never falls back to the platform admin BOT_TOKEN", src)

    def test_reseller_home_blocks_main_token_probe(self):
        from pathlib import Path

        src = Path("app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("main_token and bot_token == main_token", src)
        self.assertIn("check_bot_connection(bot_token)", src)
        # Must not call check_bot_connection() bare (would historically fall back)
        self.assertNotIn("check_bot_connection()", src)


if __name__ == "__main__":
    unittest.main()
