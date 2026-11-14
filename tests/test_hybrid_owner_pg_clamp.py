"""Hybrid Owner PG clamp — shop full, PasarGuard menus/actions from env role."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.authz import (
    authz_from_staff,
    can_pg_action,
    can_pg_page,
    can_pg_user_action,
    can_shop,
    is_platform_admin,
)
from app.services.pg_access import (
    enrich_staff_pg_from_role,
    full_pg_owner_features,
    map_pg_role_actions,
    map_pg_role_to_features,
    role_user_actions,
    staff_pg_action,
)


def _limited_role() -> dict:
    return {
        "is_owner": False,
        "permissions": {
            "users": {"read": True, "create": True, "update": False, "delete": False},
            "templates": {"read": True},
            "nodes": {"read": False},
            "hosts": {"read": False},
        },
    }


class HybridOwnerAuthzTests(unittest.TestCase):
    def test_admin_without_pg_matrix_fail_closed(self):
        ctx = authz_from_staff({"role": "admin", "username": "owner"})
        self.assertTrue(is_platform_admin(ctx))
        self.assertTrue(can_shop(ctx, "payments"))
        self.assertFalse(can_pg_page(ctx, "pg_nodes"))
        self.assertFalse(can_pg_action(ctx, "hosts", "delete"))
        self.assertFalse(can_pg_user_action(ctx, "revoke_sub"))

    def test_admin_with_limited_pg_role_clamped(self):
        role = _limited_role()
        features = map_pg_role_to_features(role)
        staff = enrich_staff_pg_from_role({"role": "admin"}, features, role)
        ctx = authz_from_staff(staff)
        self.assertTrue(can_shop(ctx, "broadcast"))
        self.assertTrue(can_pg_page(ctx, "pg_users"))
        self.assertTrue(can_pg_page(ctx, "pg_templates"))
        self.assertFalse(can_pg_page(ctx, "pg_nodes"))
        self.assertFalse(can_pg_page(ctx, "pg_hosts"))
        self.assertFalse(can_pg_page(ctx, "pg_admins"))
        self.assertTrue(staff_pg_action(staff, "users", "create"))
        self.assertFalse(staff_pg_action(staff, "users", "delete"))
        self.assertFalse(staff_pg_action(staff, "nodes", "reconnect"))

    def test_pg_owner_gets_full_features_including_admins(self):
        feats = full_pg_owner_features()
        self.assertIn("pg_nodes", feats)
        self.assertIn("pg_hosts", feats)
        self.assertIn("pg_admins", feats)
        staff = enrich_staff_pg_from_role(
            {"role": "admin", "pg_is_owner": True},
            feats,
            {"is_owner": True},
        )
        # enrich_platform path sets matrices; simulate owner matrices
        staff["pg_actions"] = map_pg_role_actions({"is_owner": True})
        staff["pg_user_actions"] = role_user_actions({"is_owner": True})
        ctx = authz_from_staff(staff)
        self.assertTrue(can_pg_page(ctx, "pg_admins"))
        self.assertTrue(can_pg_action(ctx, "nodes", "delete"))


class ResolvePlatformCapsTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_fail_closed_on_login_error(self):
        from app.services.pasarguard import PasarGuardError
        from app.services.pg_access import clear_platform_pg_capability_cache, resolve_platform_pg_capabilities

        clear_platform_pg_capability_cache()
        with patch("app.services.pasarguard.get_pg") as gp:
            client = AsyncMock()
            client.ensure_token = AsyncMock(side_effect=PasarGuardError("bad login", 401))
            gp.return_value = client
            with patch("app.config.get_settings") as gs:
                gs.return_value.pg_username = "lim"
                gs.return_value.pg_password = "x"
                gs.return_value.pg_base_url = "https://pg.example"
                caps = await resolve_platform_pg_capabilities(use_cache=False)
        self.assertFalse(caps["ok"])
        self.assertEqual(caps["features"], [])
        self.assertFalse(caps["pg_is_owner"])

    async def test_limited_admin_maps_features(self):
        from app.services.pg_access import clear_platform_pg_capability_cache, resolve_platform_pg_capabilities

        clear_platform_pg_capability_cache()
        role = _limited_role()
        role["id"] = 9
        admin = {"username": "lim", "role_id": 9, "is_sudo": False}

        with patch("app.services.pasarguard.get_pg") as gp:
            client = AsyncMock()
            client.ensure_token = AsyncMock(return_value="tok")
            client.get_admin = AsyncMock(return_value=admin)
            gp.return_value = client
            with patch(
                "app.services.pg_access.resolve_reseller_pg_features",
                new=AsyncMock(return_value=(map_pg_role_to_features(role), role)),
            ):
                with patch("app.config.get_settings") as gs:
                    gs.return_value.pg_username = "lim"
                    gs.return_value.pg_password = "x"
                    gs.return_value.pg_base_url = "https://pg.example"
                    caps = await resolve_platform_pg_capabilities(use_cache=False)
        self.assertTrue(caps["ok"])
        self.assertFalse(caps["pg_is_owner"])
        self.assertIn("pg_users", caps["features"])
        self.assertNotIn("pg_nodes", caps["features"])
        self.assertNotIn("pg_admins", caps["features"])

    async def test_sudo_admin_without_role_gets_owner_features(self):
        from app.services.pg_access import clear_platform_pg_capability_cache, resolve_platform_pg_capabilities

        clear_platform_pg_capability_cache()
        admin = {"username": "root", "is_sudo": True}
        with patch("app.services.pasarguard.get_pg") as gp:
            client = AsyncMock()
            client.ensure_token = AsyncMock(return_value="tok")
            client.get_current_admin = AsyncMock(return_value=admin)
            client.get_admin = AsyncMock(return_value=admin)
            gp.return_value = client
            with patch("app.config.get_settings") as gs:
                gs.return_value.pg_username = "root"
                gs.return_value.pg_password = "x"
                gs.return_value.pg_base_url = "https://pg.example"
                caps = await resolve_platform_pg_capabilities(use_cache=False)
        self.assertTrue(caps["ok"])
        self.assertTrue(caps["pg_is_owner"])
        self.assertIn("pg_admins", caps["features"])
        self.assertIn("pg_nodes", caps["features"])

    async def test_sudo_flag_does_not_override_non_owner_role(self):
        from app.services.pg_access import clear_platform_pg_capability_cache, resolve_platform_pg_capabilities

        clear_platform_pg_capability_cache()
        role = _limited_role()
        role["id"] = 2
        admin = {"username": "op", "is_sudo": True, "role": role}
        with patch("app.services.pasarguard.get_pg") as gp:
            client = AsyncMock()
            client.ensure_token = AsyncMock(return_value="tok")
            client.get_current_admin = AsyncMock(return_value=admin)
            gp.return_value = client
            with patch("app.config.get_settings") as gs:
                gs.return_value.pg_username = "op"
                gs.return_value.pg_password = "x"
                gs.return_value.pg_base_url = "https://pg.example"
                caps = await resolve_platform_pg_capabilities(use_cache=False)
        self.assertTrue(caps["ok"])
        self.assertFalse(caps["pg_is_owner"])
        self.assertNotIn("pg_nodes", caps["features"])
        self.assertNotIn("pg_admins", caps["features"])
        self.assertIn("pg_users", caps["features"])


if __name__ == "__main__":
    unittest.main()
