"""Phase C0 — authz foundation parity tests.

Proves new AuthzContext decisions match prior inline permission checks.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.authz import (
    AuthzContext,
    PrincipalKind,
    authz_from_shop_perm_list,
    authz_from_staff,
    can_pg_action,
    can_pg_page,
    can_pg_user_action,
    can_shop,
    is_platform_admin,
    principal_kind_from_role,
    resolve_shop_permissions_from_profile,
)
from app.services.pg_access import (
    map_pg_role_actions,
    role_user_actions,
    staff_pg_action,
    staff_pg_writes,
    staff_user_actions,
)
from app.services.resellers import has_bot_perm, has_perm


class PrincipalKindTests(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(principal_kind_from_role("admin"), PrincipalKind.PLATFORM_ADMIN)
        self.assertEqual(principal_kind_from_role("reseller"), PrincipalKind.RESELLER)
        self.assertEqual(principal_kind_from_role("pg_staff"), PrincipalKind.PG_STAFF)
        self.assertEqual(principal_kind_from_role(""), PrincipalKind.UNKNOWN)


class AuthzFromStaffTests(unittest.TestCase):
    def test_admin_shop_bypass_pg_fail_closed_without_matrix(self):
        """Hybrid: shop stays open; PG requires mapped permissions."""
        ctx = authz_from_staff({"role": "admin", "username": "owner"})
        self.assertTrue(is_platform_admin(ctx))
        self.assertTrue(can_shop(ctx, "payments"))
        self.assertFalse(can_pg_page(ctx, "pg_nodes"))
        self.assertFalse(can_pg_action(ctx, "hosts", "delete"))
        self.assertFalse(can_pg_user_action(ctx, "revoke_sub"))

    def test_admin_with_full_pg_matrix_allows(self):
        from app.services.pg_access import full_pg_owner_features, map_pg_role_actions, role_user_actions

        staff = {
            "role": "admin",
            "username": "owner",
            "pg_permissions": full_pg_owner_features(),
            "pg_actions": map_pg_role_actions({"is_owner": True}),
            "pg_user_actions": role_user_actions({"is_owner": True}),
            "pg_is_owner": True,
        }
        ctx = authz_from_staff(staff)
        self.assertTrue(can_pg_page(ctx, "pg_nodes"))
        self.assertTrue(can_pg_action(ctx, "hosts", "delete"))
        self.assertTrue(can_pg_user_action(ctx, "revoke_sub"))

    def test_reseller_shop_and_pg(self):
        staff = {
            "role": "reseller",
            "bot_user_id": 42,
            "permissions": ["dashboard", "orders"],
            "pg_permissions": ["pg_users", "pg_overview"],
            "pg_actions": {"users": {"create": True, "delete": False}},
            "pg_user_actions": {"create": True, "update": True, "delete": False},
            "pg_admin_username": "res1",
            "pg_role_id": 7,
        }
        ctx = authz_from_staff(staff)
        self.assertEqual(ctx.shop_owner_id, 42)
        self.assertEqual(ctx.pg_admin_username, "res1")
        self.assertEqual(ctx.pg_role_id, 7)
        self.assertTrue(can_shop(ctx, "dashboard"))
        self.assertFalse(can_shop(ctx, "payments"))
        self.assertTrue(can_pg_page(ctx, "pg_users"))
        self.assertFalse(can_pg_page(ctx, "pg_hosts"))
        self.assertTrue(can_pg_action(ctx, "users", "create"))
        self.assertFalse(can_pg_action(ctx, "users", "delete"))
        # Missing matrix entry → fail closed
        self.assertFalse(can_pg_action(ctx, "hosts", "create"))

    def test_pg_staff_empty_shop(self):
        ctx = authz_from_staff(
            {
                "role": "pg_staff",
                "permissions": [],
                "pg_permissions": ["pg_templates"],
                "pg_actions": {"templates": {"create": True}},
            }
        )
        self.assertFalse(can_shop(ctx, "dashboard"))
        self.assertTrue(can_pg_page(ctx, "pg_templates"))
        self.assertTrue(can_pg_action(ctx, "templates", "create"))


class LegacyParityStaffPgActionTests(unittest.TestCase):
    """staff_pg_action / staff_user_actions / staff_pg_writes == authz decisions."""

    def test_create_only_matrix(self):
        role = {
            "is_owner": False,
            "permissions": {
                "templates": {"create": True, "read": True, "delete": False, "update": False},
                "nodes": {"read": True, "reconnect": False},
            },
        }
        actions = map_pg_role_actions(role)
        staff = {"role": "pg_staff", "pg_actions": actions, "pg_writes": {"templates": True}}
        ctx = authz_from_staff(staff)
        for res, acts in actions.items():
            for act, allowed in acts.items():
                self.assertEqual(
                    staff_pg_action(staff, res, act),
                    can_pg_action(ctx, res, act),
                    f"{res}.{act}",
                )
                self.assertEqual(staff_pg_action(staff, res, act), allowed)

    def test_admin_all_true(self):
        from app.services.pg_access import full_pg_owner_features, map_pg_role_actions, map_pg_role_writes

        staff = {
            "role": "admin",
            "pg_permissions": full_pg_owner_features(),
            "pg_actions": map_pg_role_actions({"is_owner": True}),
            "pg_writes": map_pg_role_writes({"is_owner": True}),
            "pg_is_owner": True,
        }
        ctx = authz_from_staff(staff)
        self.assertTrue(staff_pg_action(staff, "nodes", "reconnect"))
        self.assertTrue(can_pg_action(ctx, "nodes", "reconnect"))
        writes = staff_pg_writes(staff)
        self.assertTrue(all(writes.values()))

    def test_user_actions_disable_follows_update(self):
        staff = {
            "role": "reseller",
            "pg_user_actions": {"update": True, "create": False, "delete": False},
        }
        ctx = authz_from_staff(staff)
        ua = staff_user_actions(staff)
        self.assertTrue(ua["disable"])
        self.assertTrue(ua["enable"])
        self.assertEqual(ua["disable"], can_pg_user_action(ctx, "disable"))
        self.assertFalse(can_pg_user_action(ctx, "create"))

    def test_fail_closed_missing_pg_actions(self):
        staff = {"role": "pg_staff"}
        self.assertFalse(staff_pg_action(staff, "users", "create"))
        self.assertFalse(can_pg_action(authz_from_staff(staff), "users", "create"))


class HasPermParityTests(unittest.TestCase):
    def test_explicit_empty_not_defaulted(self):
        profile = SimpleNamespace(is_active=True, web_permissions="")
        self.assertFalse(has_perm(profile, "payments"))
        self.assertFalse(has_perm(profile, "plans"))
        perms = resolve_shop_permissions_from_profile(profile)
        self.assertEqual(perms, [])
        self.assertFalse(can_shop(authz_from_shop_perm_list(perms), "payments"))

    def test_none_uses_default_with_core(self):
        profile = SimpleNamespace(is_active=True, web_permissions=None)
        self.assertTrue(has_perm(profile, "dashboard"))
        self.assertTrue(has_perm(profile, "payments"))
        perms = resolve_shop_permissions_from_profile(profile)
        ctx = authz_from_shop_perm_list(perms)
        self.assertTrue(can_shop(ctx, "dashboard"))
        self.assertTrue(can_shop(ctx, "shop_settings"))

    def test_inactive_denied(self):
        profile = SimpleNamespace(is_active=False, web_permissions="dashboard,payments")
        self.assertFalse(has_perm(profile, "dashboard"))
        self.assertIsNone(resolve_shop_permissions_from_profile(profile))

    def test_admin_role_bypass(self):
        profile = SimpleNamespace(is_active=True, web_permissions="")
        self.assertTrue(has_perm(profile, "payments", role="admin"))

    def test_bot_approve_receipts_alias(self):
        # payments alone is enough for the approve_receipts alias (no full-shop expand).
        profile = SimpleNamespace(is_active=True, web_permissions="payments")
        self.assertTrue(has_bot_perm(profile, "approve_receipts"))
        profile2 = SimpleNamespace(is_active=True, web_permissions="payments,dashboard")
        self.assertTrue(has_bot_perm(profile2, "approve_receipts"))
        # Explicit empty stays empty — alias still denied
        empty = SimpleNamespace(is_active=True, web_permissions="")
        self.assertFalse(has_bot_perm(empty, "approve_receipts"))


class RequirePermLogicParityTests(unittest.TestCase):
    """Simulate require_perm / require_pg_perm decision without FastAPI."""

    def _old_shop(self, user: dict, perm: str) -> bool:
        if user.get("role") == "admin":
            return True
        return perm in (user.get("permissions") or [])

    def _old_pg(self, user: dict, perm: str) -> bool:
        # Hybrid: admin also needs mapped pg_permissions (fail-closed).
        return perm in (user.get("pg_permissions") or [])

    def test_matrix(self):
        from app.services.pg_access import full_pg_owner_features

        cases = [
            {"role": "admin", "pg_permissions": full_pg_owner_features()},
            {"role": "admin"},  # fail-closed PG
            {"role": "reseller", "permissions": ["dashboard"], "pg_permissions": []},
            {
                "role": "reseller",
                "permissions": ["orders", "payments"],
                "pg_permissions": ["pg_users"],
            },
            {"role": "pg_staff", "permissions": [], "pg_permissions": ["pg_hosts", "pg_nodes"]},
            {"role": "pg_staff", "permissions": [], "pg_permissions": []},
        ]
        shop_keys = ["dashboard", "orders", "payments", "stats"]
        pg_keys = ["pg_overview", "pg_users", "pg_hosts", "pg_nodes"]
        for user in cases:
            ctx = authz_from_staff(user)
            for k in shop_keys:
                self.assertEqual(
                    self._old_shop(user, k),
                    can_shop(ctx, k),
                    f"shop {user.get('role')} {k}",
                )
            for k in pg_keys:
                self.assertEqual(
                    self._old_pg(user, k),
                    can_pg_page(ctx, k),
                    f"pg {user.get('role')} {k}",
                )


class NoSideEffectGuards(unittest.TestCase):
    def test_authz_module_has_no_db_imports(self):
        import ast
        from pathlib import Path

        tree = ast.parse(Path("app/services/authz.py").read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        top = [m for m in imported if m.startswith("app.db") or m.startswith("sqlalchemy")]
        self.assertEqual(top, [], f"C0 authz must stay I/O-free at import: {top}")

    def test_role_user_actions_still_maps(self):
        role = {
            "is_owner": False,
            "permissions": {"users": {"create": True, "update": True, "read": True}},
        }
        ua = role_user_actions(role)
        self.assertTrue(ua["create"])
        self.assertTrue(ua["disable"])


if __name__ == "__main__":
    unittest.main()
