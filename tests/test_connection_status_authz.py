"""Private monitoring is restricted to the live Owner on the main bot."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select, update

from connection_monitor_support import MonitorDatabaseCase, monitor_access

from app.db.models import ConnectionMonitorState, OrgPrincipal
from app.services.authz import AuthzContext, PrincipalKind
from app.services.connection_monitor_access import MonitorAccess
from app.services.connection_monitor_settings import monitor_settings, set_monitor_account
from app.services.resellers import DEFAULT_FEATURE_PERMS, FEATURE_PERMS


class MonitorAuthorizationTests(MonitorDatabaseCase):
    async def test_explicit_active_owner_can_initialize_private_settings(self) -> None:
        async with self.Session() as session:
            result = await monitor_settings(session, self.access)
            self.assertFalse(result.enabled)
            self.assertFalse(result.has_account)
            self.assertFalse(session.in_transaction())

    async def test_legacy_admin_staff_reseller_and_customer_cannot_read_or_configure(self) -> None:
        forbidden = [
            MonitorAccess(AuthzContext(kind=PrincipalKind.PLATFORM_ADMIN, role="admin"), True),
            monitor_access(org_principal_id=2, org_depth=1, org_parent_id=1, role="reseller", bot_user_id=2),
            monitor_access(org_principal_id=None, org_depth=None, role="user", bot_user_id=4),
            monitor_access(org_principal_id=None, org_depth=None, role="user", bot_user_id=5),
            monitor_access(org_status="disabled"),
            replace(self.access, is_main_bot=False),
        ]
        panel = AsyncMock()
        with patch("app.services.connection_monitor_accounts.get_pg", return_value=panel):
            for access in forbidden:
                async with self.Session() as session:
                    with self.subTest(access=access):
                        with self.assertRaises(ValueError):
                            await monitor_settings(session, access)
                        with self.assertRaises(ValueError):
                            await set_monitor_account(session, access, username="monitor-only")
        panel.get_user_by_username.assert_not_awaited()
        async with self.Session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(ConnectionMonitorState)), 0)

    async def test_disabled_database_owner_is_rejected_despite_cached_active_context(self) -> None:
        async with self.Session() as session:
            await session.execute(update(OrgPrincipal).where(OrgPrincipal.id == 1).values(status="disabled"))
            await session.commit()
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await monitor_settings(session, self.access)

    async def test_shop_permissions_do_not_grant_owner_authority(self) -> None:
        access = monitor_access(org_principal_id=2, org_depth=1, org_parent_id=1,
                                role="reseller", permissions=["connection_status", "connection_status_manage"])
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await monitor_settings(session, access)

    async def test_a_denied_feature_permission_prevents_private_reads(self) -> None:
        with patch("app.services.connection_monitor_access.can_shop", return_value=False):
            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await monitor_settings(session, self.access)

    async def test_permissions_are_declared_without_a_default_reseller_grant(self) -> None:
        keys = {key for key, _label in FEATURE_PERMS}
        self.assertTrue({"connection_status", "connection_status_manage"} <= keys)
        self.assertNotIn("connection_status", DEFAULT_FEATURE_PERMS.split(","))
        self.assertNotIn("connection_status_manage", DEFAULT_FEATURE_PERMS.split(","))
