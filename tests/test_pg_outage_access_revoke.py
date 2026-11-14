"""Regression test: a temporary PasarGuard outage must never permanently
revoke a pg_staff web account.

``PasarGuardClient.get_admin()`` used to swallow every lookup exception
internally (404 "not found" and network/timeout/5xx errors alike) and just
return ``None`` either way. ``fetch_pg_admin_gate`` then classified that as
``"missing"`` (admin fully deleted), and ``enforce_pg_admin_web_gate`` would
permanently delete the ``PgStaffAccess`` row for a legitimate staff member
just because PasarGuard happened to be briefly down/unreachable.

The fix adds ``get_admin_gate()`` which distinguishes a clean 404 (genuinely
missing) from any transport/server error (unreachable), and
``fetch_pg_admin_gate`` now trusts that distinction instead of re-deriving it
from a already-ambiguous ``None``.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.pasarguard import PasarGuardClient, PasarGuardError


def _make_client() -> PasarGuardClient:
    return PasarGuardClient(username="owner", password="x")


class AdminGateNetworkErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        pass

    async def test_confirmed_404_everywhere_is_missing(self):
        client = _make_client()
        try:
            with patch.object(
                client,
                "request",
                new=AsyncMock(side_effect=PasarGuardError("not found", 404)),
            ), patch.object(client, "get_admins", new=AsyncMock(return_value=[])):
                gate, admin = await client.get_admin_gate("some_admin")
            self.assertEqual(gate, "missing")
            self.assertIsNone(admin)
        finally:
            await client.close()

    async def test_network_timeout_is_unreachable_not_missing(self):
        client = _make_client()
        try:
            with patch.object(
                client,
                "request",
                new=AsyncMock(side_effect=TimeoutError("connect timeout")),
            ), patch.object(
                client, "get_admins", new=AsyncMock(side_effect=TimeoutError("connect timeout"))
            ):
                gate, admin = await client.get_admin_gate("some_admin")
            self.assertEqual(gate, "unreachable")
            self.assertIsNone(admin)
        finally:
            await client.close()

    async def test_server_5xx_is_unreachable_not_missing(self):
        client = _make_client()
        try:
            with patch.object(
                client,
                "request",
                new=AsyncMock(side_effect=PasarGuardError("bad gateway", 502)),
            ), patch.object(
                client,
                "get_admins",
                new=AsyncMock(side_effect=PasarGuardError("bad gateway", 502)),
            ):
                gate, admin = await client.get_admin_gate("some_admin")
            self.assertEqual(gate, "unreachable")
        finally:
            await client.close()

    async def test_found_admin_returns_ok(self):
        client = _make_client()
        try:
            with patch.object(
                client,
                "request",
                new=AsyncMock(return_value={"username": "some_admin", "id": 5, "is_active": True}),
            ):
                gate, admin = await client.get_admin_gate("some_admin")
            self.assertEqual(gate, "ok")
            self.assertEqual((admin or {}).get("id"), 5)
        finally:
            await client.close()

    async def test_current_admin_self_is_ok_when_directory_forbidden(self):
        client = _make_client()
        try:
            async def _req(method, path, **kwargs):
                if path == "/api/admin":
                    return {"username": "84104", "id": 12, "is_active": True}
                raise PasarGuardError("forbidden", 403)

            with patch.object(client, "request", new=AsyncMock(side_effect=_req)):
                gate, admin = await client.get_admin_gate("84104")
            self.assertEqual(gate, "ok")
            self.assertEqual((admin or {}).get("username"), "84104")
        finally:
            await client.close()

    async def test_current_admin_self_is_not_another_username(self):
        client = _make_client()
        try:
            async def _req(method, path, **kwargs):
                if path == "/api/admin":
                    return {"username": "owner", "id": 1, "is_active": True}
                raise PasarGuardError("not found", 404)

            with patch.object(
                client, "request", new=AsyncMock(side_effect=_req)
            ), patch.object(client, "get_admins", new=AsyncMock(return_value=[])):
                gate, admin = await client.get_admin_gate("alice")
            self.assertEqual(gate, "missing")
            self.assertIsNone(admin)
        finally:
            await client.close()

    async def test_current_admin_403_then_confirmed_404_is_missing(self):
        client = _make_client()
        try:
            async def _req(method, path, **kwargs):
                if path == "/api/admin":
                    raise PasarGuardError("forbidden", 403)
                raise PasarGuardError("not found", 404)

            with patch.object(
                client, "request", new=AsyncMock(side_effect=_req)
            ), patch.object(client, "get_admins", new=AsyncMock(return_value=[])):
                gate, admin = await client.get_admin_gate("some_admin")
            self.assertEqual(gate, "missing")
            self.assertIsNone(admin)
        finally:
            await client.close()


class PgStaffOutageDoesNotRevokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_gate_unreachable_never_classified_as_missing(self):
        from app.services.pg_staff_access import fetch_pg_admin_gate

        with patch("app.services.pasarguard.get_pg") as mock_get_pg:
            fake_client = AsyncMock()
            fake_client.get_admin_gate = AsyncMock(return_value=("unreachable", None))
            mock_get_pg.return_value = fake_client

            gate, admin = await fetch_pg_admin_gate("some_admin")
        self.assertEqual(gate, "unreachable")
        self.assertIsNone(admin)

    async def test_enforce_web_gate_does_not_revoke_on_outage(self):
        from app.services.pg_staff_access import enforce_pg_admin_web_gate

        with patch(
            "app.services.pg_staff_access.fetch_pg_admin_gate",
            new=AsyncMock(return_value=("unreachable", None)),
        ), patch(
            "app.services.pg_staff_access.revoke_web_access", new=AsyncMock()
        ) as mock_revoke:
            allowed, err = await enforce_pg_admin_web_gate(
                session=None, pg_username=f"outage_probe_{id(self)}"
            )

        self.assertFalse(allowed)
        self.assertIsNotNone(err)
        mock_revoke.assert_not_called()

    async def test_enforce_web_gate_revokes_on_confirmed_missing(self):
        from app.services.pg_staff_access import enforce_pg_admin_web_gate

        with patch(
            "app.services.pg_staff_access.fetch_pg_admin_gate",
            new=AsyncMock(return_value=("missing", None)),
        ), patch(
            "app.services.pg_staff_access.revoke_web_access", new=AsyncMock()
        ) as mock_revoke:
            allowed, err = await enforce_pg_admin_web_gate(
                session=None, pg_username=f"deleted_probe_{id(self)}"
            )

        self.assertFalse(allowed)
        mock_revoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
