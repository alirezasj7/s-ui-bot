"""Final pre-merge RBAC security: capability-based, future roles, no owner bypass."""
from __future__ import annotations

import pathlib
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pg_access import (
    map_pg_role_actions,
    map_pg_role_to_features,
    map_pg_role_writes,
    role_user_actions,
    staff_pg_action,
    staff_user_actions,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
PG_PAGES = (ROOT / "app" / "api" / "pg_pages.py").read_text(encoding="utf-8")
PG_ACCESS = (ROOT / "app" / "services" / "pg_access.py").read_text(encoding="utf-8")


def _dashagh_role(**user_perms) -> dict:
    """Future custom PG role — permissions only, never by name."""
    return {
        "id": 99,
        "name": "dashagh",
        "is_owner": False,
        "permissions": {
            "system": {"read": True},
            "users": {
                "read": True,
                "create": user_perms.get("create", True),
                "update": user_perms.get("update", False),
                "delete": user_perms.get("delete", False),
                "reset_usage": False,
                "revoke_sub": False,
            },
            "hosts": {"read": True, "create": False, "update": False, "delete": False},
            "nodes": {"read": False, "create": False, "update": False, "delete": False, "reconnect": False},
            "templates": {"read": True, "create": False, "update": False, "delete": False},
            "groups": {"read": True, "create": False, "update": False, "delete": False},
        },
    }


class NoRoleNameHardcoding(unittest.TestCase):
    def test_authz_paths_do_not_gate_on_pg_role_names(self):
        needles = (
            '== "administrator"',
            "== 'administrator'",
            '== "operator"',
            "== 'operator'",
            '== "dashagh"',
            'name == "administrator"',
            'role_name == "administrator"',
        )
        for path in (
            ROOT / "app/services/pg_access.py",
            ROOT / "app/services/authz.py",
            ROOT / "app/api/pg_pages.py",
            ROOT / "app/bot",
        ):
            files = [path] if path.is_file() else list(path.rglob("*.py"))
            for f in files:
                text = f.read_text(encoding="utf-8")
                for n in needles:
                    self.assertNotIn(n, text, msg=f"{f} gates on role name via {n}")

    def test_mapping_uses_permissions_matrix_not_name(self):
        self.assertIn("role.get(\"permissions\")", PG_ACCESS)
        self.assertIn("role.get(\"is_owner\")", PG_ACCESS)
        self.assertNotIn('role.get("name") ==', PG_ACCESS)


class FutureRoleFailClosed(unittest.TestCase):
    def test_dashagh_users_create_only(self):
        role = _dashagh_role(create=True)
        features = map_pg_role_to_features(role)
        self.assertIn("pg_users", features)
        self.assertIn("pg_overview", features)
        self.assertNotIn("pg_nodes", features)  # no node actions at all
        self.assertIn("pg_hosts", features)  # read-only still lists the page
        actions = map_pg_role_actions(role)
        self.assertTrue(actions["users"]["create"])
        self.assertFalse(actions["users"]["update"])
        self.assertFalse(actions["hosts"]["create"])
        self.assertFalse(actions["hosts"]["delete"])
        self.assertFalse(actions["nodes"]["reconnect"])
        ua = role_user_actions(role)
        self.assertTrue(ua["create"])
        self.assertFalse(ua["update"])
        self.assertFalse(ua["delete"])

    def test_empty_permissions_deny_all(self):
        role = {"id": 1, "name": "dashagh", "is_owner": False, "permissions": {}}
        self.assertEqual(map_pg_role_to_features(role), [])
        actions = map_pg_role_actions(role)
        for res, flags in actions.items():
            self.assertTrue(all(v is False for v in flags.values()), msg=res)
        writes = map_pg_role_writes(role)
        self.assertTrue(all(v is False for v in writes.values()))

    def test_unknown_role_name_does_not_grant_access(self):
        """Name alone never unlocks capabilities."""
        role = {"id": 7, "name": "administrator", "is_owner": False, "permissions": {}}
        self.assertEqual(map_pg_role_to_features(role), [])
        self.assertFalse(map_pg_role_actions(role)["users"]["create"])


class RestrictedAdminBoundaries(unittest.TestCase):
    def test_staff_dict_with_limited_actions(self):
        staff = {
            "role": "reseller",
            "bot_user_id": 3,
            "pg_actions": map_pg_role_actions(_dashagh_role()),
            "pg_user_actions": role_user_actions(_dashagh_role()),
            "pg_writes": map_pg_role_writes(_dashagh_role()),
            "pg_permissions": map_pg_role_to_features(_dashagh_role()),
        }
        self.assertTrue(staff_user_actions(staff)["create"])
        self.assertFalse(staff_user_actions(staff)["update"])
        self.assertFalse(staff_pg_action(staff, "hosts", "create"))
        self.assertFalse(staff_pg_action(staff, "hosts", "delete"))
        self.assertFalse(staff_pg_action(staff, "nodes", "create"))
        self.assertFalse(staff_pg_action(staff, "nodes", "reconnect"))

    def test_owner_full_access(self):
        from app.services.pg_access import (
            full_pg_owner_features,
            map_pg_role_actions,
            role_user_actions,
        )

        admin = {
            "role": "admin",
            "pg_permissions": full_pg_owner_features(),
            "pg_actions": map_pg_role_actions({"is_owner": True}),
            "pg_user_actions": role_user_actions({"is_owner": True}),
            "pg_is_owner": True,
        }
        self.assertTrue(staff_pg_action(admin, "hosts", "delete"))
        self.assertTrue(staff_pg_action(admin, "nodes", "reconnect"))
        self.assertTrue(staff_user_actions(admin)["delete"])
        # Hybrid: bare admin session without enrichment is fail-closed for PG
        self.assertFalse(staff_pg_action({"role": "admin"}, "hosts", "delete"))


class HostsDeleteExactAction(unittest.TestCase):
    def test_delete_requires_hosts_delete_not_update(self):
        src = PG_PAGES
        fn = src.split("async def pg_hosts_delete", 1)[1].split("async def ", 1)[0]
        self.assertIn('staff_pg_action(staff, "hosts", "delete")', fn)
        self.assertNotIn('staff_pg_action(staff, "hosts", "update")', fn)

    def test_ui_flags_exact_not_can_write(self):
        for name in ("pg_hosts.html", "pg_templates.html", "pg_groups.html"):
            html = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
            self.assertNotIn("can_write", html)
            self.assertIn("can_create", html)
            self.assertIn("can_update", html)


class AdminCreateNoOwnerEscalation(unittest.TestCase):
    def test_server_rejects_is_owner_role(self):
        fn = PG_PAGES.split("async def pg_admins_create", 1)[1].split(
            "async def pg_admins_", 1
        )[0]
        self.assertIn('chosen.get("is_owner")', fn)
        self.assertIn("نمی‌توان نقش ادمین اصلی", fn)
        self.assertIn("ساخت ادمین با دسترسی sudo", fn)
        # No fail-open retry without role
        self.assertNotIn('payload.pop("role_id"', fn)

    def test_template_hides_owner_roles(self):
        html = (ROOT / "app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn("if not r.get('is_owner')", html)


class NoOwnerTokenOnStaffWrites(unittest.TestCase):
    def test_staff_mutations_use_staff_pg(self):
        # Spot-check sensitive resources
        for path in (
            "/pg/users",
            "/pg/templates",
            "/pg/groups",
            "/pg/hosts",
            "/pg/nodes",
        ):
            self.assertIn(f'@app.post("{path}', PG_PAGES)
        self.assertIn("await _staff_pg(", PG_PAGES)
        # Env client for platform admin; as_owner gated by pg_is_owner (Hybrid)
        fn = PG_PAGES[
            PG_PAGES.find("async def _staff_pg") : PG_PAGES.find("async def _assert_owned_user")
        ]
        self.assertIn("return get_pg(), bool(staff.get(\"pg_is_owner\"))", fn)
        self.assertEqual(fn.count("return get_pg(), True"), 0)
        self.assertIn("is_platform_admin(staff)", fn)


class ResellerParity(unittest.TestCase):
    def test_bot_shop_acl_uses_web_permissions(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        self.assertIn("identical to web shop ACL", src)
        self.assertIn("web_permissions", src)
        self.assertIn("bot_permissions = profile.web_permissions", src)

    def test_reseller_pg_features_from_live_role_not_plan_flags(self):
        """PG page ACL comes from PasarGuard role matrix, not local plan name."""
        src = (ROOT / "app/services/pg_access.py").read_text(encoding="utf-8")
        self.assertIn("resolve_reseller_pg_features", src)
        self.assertIn("map_pg_role_actions", src)


if __name__ == "__main__":
    unittest.main()
