"""Account setup encrypts references and excludes customer accounts without network transactions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update

from connection_monitor_support import MonitorDatabaseCase

from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget, OrgPrincipal, UserService
from app.services.connection_monitor_settings import (
    monitor_settings,
    reveal_monitor_token,
    set_monitor_account,
)
from app.services.connection_monitor_accounts import MonitorAccountError
from app.services.connection_monitor_errors import monitor_error_message
from app.services.pasarguard import PasarGuardError
from app.services.secret_box import decrypt_secret


TOKEN = "synthetic-monitor-token-123456"


def panel_account(**changes: object) -> dict[str, object]:
    return {"id": 900, "username": "monitor-only", "status": "active", "admin": {"username": "panel-owner"},
            "used_traffic": 0, "data_limit": 0, "expire": None,
            "subscription_url": f"https://panel.example/sub/{TOKEN}", **changes}


class MonitorSettingsTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.panel = SimpleNamespace(get_user_by_username=AsyncMock(return_value=panel_account()),
                                     get_current_admin=AsyncMock(return_value={"role": {"id": 1, "is_owner": True}, "username": "panel-owner"}))
        for patcher in [
            patch("app.services.connection_monitor_accounts.get_pg", return_value=self.panel),
            patch("app.services.secret_box._root_secret", return_value=b"synthetic-monitor-tests-secret-never-production"),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_setup_accepts_accessible_test_user_without_panel_owner_endpoint(self) -> None:
        self.panel.get_current_admin.side_effect = PermissionError("Owner endpoint is unavailable")
        self.panel.get_user_by_username.return_value = panel_account(admin={"username": "another-admin"})
        async with self.Session() as session:
            result = await set_monitor_account(session, self.access, username="monitor-only")
        self.assertTrue(result.has_account)
        self.panel.get_current_admin.assert_not_awaited()

    async def test_setup_keeps_the_canonical_panel_username_when_case_differs(self) -> None:
        self.panel.get_user_by_username.return_value = panel_account(username="Monitor-Only", admin=None)
        async with self.Session() as session:
            await set_monitor_account(session, self.access, username="monitor-only")
            stored = await session.scalar(select(ConnectionMonitorState))
            self.assertEqual(stored.pg_username, "Monitor-Only")

    async def test_setup_returns_specific_safe_panel_errors(self) -> None:
        for status, code in ((404, "not_found"), (401, "panel_denied"), (403, "panel_denied"), (503, "panel_unavailable")):
            self.panel.get_user_by_username.side_effect = PasarGuardError(TOKEN, status, {"detail": TOKEN})
            async with self.Session() as session:
                with self.subTest(status=status), self.assertRaises(MonitorAccountError) as caught:
                    await set_monitor_account(session, self.access, username="monitor-only")
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn(TOKEN, monitor_error_message(caught.exception))
            self.assertNotEqual(monitor_error_message(caught.exception), monitor_error_message(RuntimeError(TOKEN)))

    async def test_setup_explains_inactive_expired_and_exhausted_test_users(self) -> None:
        for changes, code in (({"status": "disabled"}, "inactive"),
                              ({"expire": "2020-01-01T00:00:00Z"}, "expired"),
                              ({"used_traffic": 1, "data_limit": 1}, "traffic_exhausted"),
                              ({"subscription_url": ""}, "invalid_subscription")):
            self.panel.get_user_by_username.return_value = panel_account(**changes)
            async with self.Session() as session:
                with self.subTest(code=code), self.assertRaises(MonitorAccountError) as caught:
                    await set_monitor_account(session, self.access, username="monitor-only")
            self.assertEqual(caught.exception.code, code)

    async def test_test_user_role_is_not_used_to_bypass_customer_account_exclusion(self) -> None:
        self.panel.get_user_by_username.return_value = panel_account(admin=None)
        async with self.Session() as session:
            session.add(UserService(bot_user_id=5, pg_username="MONITOR-ONLY", remark="sold"))
            await session.commit()
            with self.assertRaises(MonitorAccountError) as caught:
                await set_monitor_account(session, self.access, username="monitor-only")
            self.assertEqual(caught.exception.code, "customer_account")

    async def test_setup_is_disabled_by_default_and_never_stores_or_returns_plaintext(self) -> None:
        async with self.Session() as session:
            result = await set_monitor_account(session, self.access, username="monitor-only")
            self.assertEqual((result.enabled, result.pg_user_id, result.has_account), (False, 900, True))
            self.assertNotIn(TOKEN, repr(result))
            state = await session.scalar(select(ConnectionMonitorState))
            self.assertNotIn(TOKEN, state.subscription_token_enc)
            self.assertEqual(await asyncio.to_thread(decrypt_secret, state.subscription_token_enc), TOKEN)
            self.assertEqual(await reveal_monitor_token(state.subscription_token_enc), TOKEN)

    async def test_no_database_transaction_is_open_during_panel_read(self) -> None:
        async with self.Session() as session:
            async def read(_username: str) -> dict[str, object]:
                self.assertFalse(session.in_transaction())
                return panel_account()

            self.panel.get_user_by_username.side_effect = read
            await set_monitor_account(session, self.access, username="monitor-only")
            self.assertFalse(session.in_transaction())

    async def test_panel_role_does_not_restrict_an_accessible_test_user(self) -> None:
        for admin in ({"is_owner": False}, {"role": {"is_owner": False}, "is_owner": True}):
            self.panel.get_current_admin.return_value = admin
            async with self.Session() as session:
                result = await set_monitor_account(session, self.access, username="monitor-only")
            self.assertTrue(result.has_account)
        self.panel.get_current_admin.assert_not_awaited()

    async def test_hostile_account_names_never_become_panel_paths(self) -> None:
        async with self.Session() as session:
            for username in ("../admin", "user/other", "user?token=secret", "user\\name", "user\nname"):
                with self.subTest(username=username), self.assertRaises(ValueError):
                    await set_monitor_account(session, self.access, username=username)
        self.panel.get_current_admin.assert_not_called()
        self.panel.get_user_by_username.assert_not_called()

    async def test_existing_target_claims_and_publication_are_invalidated_on_account_setup(self) -> None:
        async with self.Session() as session:
            session.add_all([
                ConnectionMonitorTarget(pg_host_id=41, test_enabled=True, is_public=True, public_name="عمومی",
                                        generation="old", endpoint_count=1, claim_token="old-claim"),
                ConnectionMonitorTarget(reseller_id=2, pg_host_id=41, test_enabled=True, is_public=True,
                                        public_name="فروشگاه دوم", generation="shop-generation", endpoint_count=1),
            ])
            await session.commit()
            await set_monitor_account(session, self.access, username="monitor-only")
        async with self.Session() as session:
            rows = (await session.scalars(select(ConnectionMonitorTarget).order_by(ConnectionMonitorTarget.id).limit(2))).all()
            self.assertEqual((rows[0].generation, rows[0].endpoint_count, rows[0].is_public, rows[0].claim_token), ("", 0, False, None))
            self.assertEqual((rows[1].generation, rows[1].is_public), ("shop-generation", True))

    async def test_owner_revoked_during_network_wait_cannot_mutate_account(self) -> None:
        async def revoke(_username: str) -> dict[str, object]:
            async with self.Session() as other:
                await other.execute(update(OrgPrincipal).where(OrgPrincipal.id == 1).values(status="disabled"))
                await other.commit()
            return panel_account()

        self.panel.get_user_by_username.side_effect = revoke
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await set_monitor_account(session, self.access, username="monitor-only")
            self.assertFalse(session.in_transaction())
        async with self.Session() as session:
            self.assertIsNone((await session.scalar(select(ConnectionMonitorState))).pg_user_id)

    async def test_customer_accounts_in_either_shop_are_excluded_without_changing_the_service(self) -> None:
        for customer in (4, 5):
            async with self.Session() as session:
                service = UserService(bot_user_id=customer, pg_user_id=900, pg_username="monitor-only", remark="sold")
                session.add(service)
                await session.commit()
                service_id = service.id
            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await set_monitor_account(session, self.access, username="monitor-only")
                self.assertFalse(session.in_transaction())
            async with self.Session() as session:
                service = await session.get(UserService, service_id)
                self.assertEqual(service.remark, "sold")
                await session.delete(service)
                await session.commit()

    async def test_invalid_account_states_and_numbers_fail_without_leaking_payload(self) -> None:
        changes = [
            {"status": "on_hold"}, {"status": "disabled"}, {"id": True}, {"id": 0}, {"id": 2147483648},
            {"username": "different-account"},
            {"used_traffic": True}, {"used_traffic": -1}, {"data_limit": -1}, {"data_limit": 2**63},
            {"used_traffic": 10, "data_limit": 10}, {"expire": "2020-01-01T00:00:00Z"},
            {"expire": float("nan")}, {"expire": 10**100}, {"expire": "2099-01-01T00:00:00"},
            {"subscription_url": 123}, {"subscription_url": ""},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.panel.get_user_by_username.return_value = panel_account(**change)
                async with self.Session() as session:
                    with self.assertRaises(ValueError) as caught:
                        await set_monitor_account(session, self.access, username="monitor-only")
                    self.assertNotIn(TOKEN, str(caught.exception))

    async def test_legacy_customer_account_without_panel_id_is_excluded_by_case_insensitive_username(self) -> None:
        for customer in (4, 5):
            async with self.Session() as session:
                service = UserService(bot_user_id=customer, pg_user_id=None, pg_username="MONITOR-ONLY", remark="legacy-sold")
                session.add(service)
                await session.commit()
                service_id = service.id
            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await set_monitor_account(session, self.access, username="monitor-only")
            async with self.Session() as session:
                service = await session.get(UserService, service_id)
                self.assertEqual(service.remark, "legacy-sold")
                self.assertIsNone(service.pg_user_id)
                await session.delete(service)
                await session.commit()

    async def test_panel_timeout_is_a_safe_setup_failure(self) -> None:
        self.panel.get_user_by_username.side_effect = TimeoutError(TOKEN)
        async with self.Session() as session:
            with self.assertRaises(ValueError) as caught:
                await set_monitor_account(session, self.access, username="monitor-only")
            self.assertNotIn(TOKEN, str(caught.exception))
            self.assertIsInstance(caught.exception, MonitorAccountError)
            self.assertEqual(caught.exception.code, "panel_timeout")

    async def test_unreadable_or_unencryptable_secret_stops_setup(self) -> None:
        with patch("app.services.connection_monitor_settings.encrypt_secret", return_value=None):
            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await set_monitor_account(session, self.access, username="monitor-only")
        with patch("app.services.connection_monitor_settings.decrypt_secret", return_value=None):
            with self.assertRaises(ValueError):
                await reveal_monitor_token("unreadable")

    async def test_repeated_settings_initialization_keeps_one_state(self) -> None:
        async with self.Session() as session:
            first = await monitor_settings(session, self.access)
            second = await monitor_settings(session, self.access)
        self.assertEqual(first, second)
