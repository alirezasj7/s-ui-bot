"""Regression test: PasarGuard bot mutation handlers must check the exact
resource action (create/update/delete/reconnect), not just page-level access.

Previously ``_require_users``/``_require_nodes`` accepted an ``action``
kwarg but ~50 call sites across ``admin_pg_users.py`` /
``admin_pg_nodes.py`` never passed it, so any admin who could see the
"users"/"nodes" page in the bot could invoke create/update/delete/reconnect
regardless of their actual PasarGuard permissions (defense-in-depth gap for
Hybrid Owner setups with a non-owner env PG account). These tests call the
real handler functions with a PasarGuard permission matrix that only grants
"read", and assert every mutation is refused *before* it reaches the
PasarGuard client.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _fake_callback(data: str):
    cb = SimpleNamespace()
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = None
    return cb


class BotPgUsersActionMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_action_gate(self, coro_factory, *, allow_action: str | None):
        """Patch can_platform_pg_action to allow only ``allow_action`` (or
        nothing when None), and can_platform_pg_page/_is_admin to always
        allow, then run the handler and return the mocked PasarGuard client."""
        import app.bot.handlers.admin_pg_users as mod

        fake_pg = AsyncMock()
        with patch.object(mod, "_is_admin", return_value=True), patch.object(
            mod, "can_platform_pg_page", new=AsyncMock(return_value=True)
        ), patch.object(
            mod,
            "can_platform_pg_action",
            new=AsyncMock(side_effect=lambda _u, _r, a: a == allow_action),
        ), patch.object(mod, "get_pg", return_value=fake_pg):
            await coro_factory(mod)
        return fake_pg

    async def test_reset_blocked_without_update_permission(self):
        import app.bot.handlers.admin_pg_users as mod

        cb = _fake_callback("adm:pg:reset:5")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_reset(cb, db_user=object()), allow_action="create"
        )
        fake_pg.reset_user_by_id.assert_not_called()
        cb.answer.assert_awaited()

    async def test_reset_allowed_with_update_permission(self):
        """Phase 4C: reset is Principal-gated. Missing session fail-closes (no PG call)."""
        cb = _fake_callback("adm:pg:reset:5")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_reset(cb, db_user=object()), allow_action="update"
        )
        fake_pg.reset_user_by_id.assert_not_called()

    async def test_disable_blocked_without_update_permission(self):
        cb = _fake_callback("adm:pg:dis:7")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_dis(cb, db_user=object()), allow_action="delete"
        )
        fake_pg.set_disabled_by_id.assert_not_called()

    async def test_delete_user_blocked_without_delete_permission(self):
        import app.bot.handlers.admin_pg_users as mod

        cb = _fake_callback("adm:pg:u:9:del")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_user_del(cb, state=AsyncMock(), db_user=object()),
            allow_action="update",
        )
        fake_pg.delete_user_by_id.assert_not_called()

    async def test_delete_user_allowed_with_delete_permission(self):
        """Phase 4C: delete is Principal-gated. Missing session fail-closes (no PG call)."""
        cb = _fake_callback("adm:pg:u:9:del")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_user_del(cb, state=AsyncMock(), db_user=object()),
            allow_action="delete",
        )
        fake_pg.delete_user_by_id.assert_not_called()

    async def test_read_only_detail_view_does_not_require_action_permission(self):
        """Phase 4B: detail is Principal-gated. Missing session fail-closes (no PG call)."""
        import app.bot.handlers.admin_pg_users as mod

        cb = _fake_callback("adm:pg:u:9")
        cb.message = SimpleNamespace()
        fake_pg = AsyncMock()
        fake_pg.get_user_by_id = AsyncMock(return_value={"id": 9})
        with patch.object(mod, "_is_admin", return_value=True), patch.object(
            mod, "can_platform_pg_page", new=AsyncMock(return_value=True)
        ), patch.object(
            mod, "can_platform_pg_action", new=AsyncMock(return_value=False)
        ), patch.object(mod, "get_pg", return_value=fake_pg), patch.object(
            mod, "_show_user_card", new=AsyncMock()
        ) as show_card:
            await mod.pg_user_detail(cb, db_user=object())
        show_card.assert_not_awaited()
        fake_pg.get_user_by_id.assert_not_called()
        cb.answer.assert_awaited()


class BotPgNodesActionMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_action_gate(self, coro_factory, *, allow_action: str | None):
        import app.bot.handlers.admin_pg_nodes as mod

        fake_pg = AsyncMock()
        fake_pg.get_nodes = AsyncMock(return_value=[])
        with patch.object(mod, "_is_admin", return_value=True), patch.object(
            mod, "can_platform_pg_page", new=AsyncMock(return_value=True)
        ), patch.object(
            mod,
            "can_platform_pg_action",
            new=AsyncMock(side_effect=lambda _u, _r, a: a == allow_action),
        ), patch.object(mod, "get_pg", return_value=fake_pg):
            await coro_factory(mod)
        return fake_pg

    async def test_delete_node_blocked_without_delete_permission(self):
        import app.bot.handlers.admin_pg_nodes as mod

        cb = _fake_callback("adm:pg:ndel:3")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_node_delete(cb, db_user=object()), allow_action="update"
        )
        fake_pg.delete_node.assert_not_called()

    async def test_delete_node_allowed_with_delete_permission(self):
        """Phase 4D: delete is Principal-gated. Missing session fail-closes (no PG call)."""
        cb = _fake_callback("adm:pg:ndel:3")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_node_delete(cb, db_user=object()), allow_action="delete"
        )
        fake_pg.delete_node.assert_not_called()

    async def test_reconnect_blocked_without_reconnect_permission(self):
        cb = _fake_callback("adm:pg:recon:4")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_recon(cb, db_user=object()), allow_action="update"
        )
        fake_pg.reconnect_node.assert_not_called()

    async def test_reconnect_allowed_with_reconnect_permission(self):
        """Phase 4D: reconnect is Principal-gated. Missing session fail-closes (no PG call)."""
        cb = _fake_callback("adm:pg:recon:4")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_recon(cb, db_user=object()), allow_action="reconnect"
        )
        fake_pg.reconnect_node.assert_not_called()

    async def test_node_toggle_blocked_without_update_permission(self):
        cb = _fake_callback("adm:pg:ntog:8")
        fake_pg = await self._run_with_action_gate(
            lambda m: m.pg_node_toggle(cb, db_user=object()), allow_action="delete"
        )
        fake_pg.modify_node.assert_not_called()


if __name__ == "__main__":
    unittest.main()
