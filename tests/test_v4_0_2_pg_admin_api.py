"""v4.0.2 — PG admin API case/by-id fix + node/admin parity."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


class ModifyAdminByIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_by_id_after_case_insensitive_lookup(self):
        from app.services.pasarguard import PasarGuardClient

        client = PasarGuardClient.__new__(PasarGuardClient)
        client.get_admin = AsyncMock(
            return_value={"id": 84104, "username": "Hamidrt"}
        )
        client.request = AsyncMock(return_value={"ok": True})
        out = await PasarGuardClient.modify_admin(
            client, "hamidrt", {"password": "AaBb12!secretXX"}
        )
        self.assertEqual(out, {"ok": True})
        client.request.assert_awaited_once_with(
            "PUT", "/api/admin/by-id/84104", json={"password": "AaBb12!secretXX"}
        )

    async def test_falls_back_to_exact_username_path(self):
        from app.services.pasarguard import PasarGuardClient, PasarGuardError

        client = PasarGuardClient.__new__(PasarGuardClient)
        client.get_admin = AsyncMock(
            return_value={"id": 7, "username": "Clock"}
        )

        async def _req(method, path, **kwargs):
            if "by-id" in path:
                raise PasarGuardError("gone", 404)
            if "by-username" in path:
                raise PasarGuardError("gone", 405)
            return {"username": "Clock"}

        client.request = AsyncMock(side_effect=_req)
        out = await PasarGuardClient.modify_admin(
            client, "clock", {"password": "AaBb12!secretXX"}
        )
        self.assertEqual(out["username"], "Clock")
        paths = [c.args[1] for c in client.request.await_args_list]
        self.assertIn("/api/admin/Clock", paths)


class AutoWebOnCreateContract(unittest.TestCase):
    def test_create_route_grants_web(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def pg_admins_create") : src.find(
                "async def pg_admins_web_access_legacy"
            )
        ]
        self.assertIn("grant_web_access", fn)
        self.assertIn("grant_web", fn)
        self.assertIn("permission_overrides", fn)
        self.assertIn("data_limit", fn)


class NodeParityContract(unittest.TestCase):
    def test_node_routes_and_template(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("pg_nodes_reconnect_all", src)
        self.assertIn("pg_node_sync", src)
        self.assertIn("pg_node_reset", src)
        self.assertIn("pg_node_delete", src)
        self.assertIn("pg_nodes_create", src)
        self.assertIn("create_node", (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8"))
        tpl = (ROOT / "app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn("اتصال مجدد همه", tpl)
        self.assertIn("همگام‌سازی", tpl)
        self.assertIn("ساخت نود", tpl)

    def test_role_actions_include_node_delete(self):
        src = (ROOT / "app/services/pg_access.py").read_text(encoding="utf-8")
        block = src[src.find("def map_pg_role_actions") : src.find("def map_pg_role_writes")]
        self.assertIn('"delete"', block)
        self.assertIn("nodes", block)


class AdminCreateTemplate(unittest.TestCase):
    def test_limits_and_auto_web_in_form(self):
        tpl = (ROOT / "app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn("grant_web", tpl)
        self.assertIn('name="data_limit_gb"', tpl)
        self.assertIn('name="max_users"', tpl)
        self.assertIn('name="max_hwid_per_user"', tpl)


if __name__ == "__main__":
    unittest.main()
