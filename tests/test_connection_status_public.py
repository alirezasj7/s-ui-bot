"""Published status is shop-scoped, bounded, read-only and free of diagnostics."""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from sqlalchemy import Connection, event, select

from connection_monitor_support import MonitorDatabaseCase

from app.bot.connection_status_public_ui import CATALOG_STALE_NOTICE, public_status_text
from app.db.models import ConnectionMonitorSnapshot, ConnectionMonitorState, ConnectionMonitorTarget, OrgPrincipal, UserService
from app.services.connection_status import PublicConnectionPage, public_connection_page
from app.services.users import DEFAULT_SETTINGS, reset_shop_reseller_id, set_shop_reseller_id


class PublicConnectionTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with self.Session() as session:
            session.add_all([ConnectionMonitorState(reseller_id=shop_id, enabled=True, pg_user_id=900 + index, pg_username=f"monitor-{index}",
                                                   subscription_token_enc="encrypted-sensitive-token", account_revision="one", catalog_synced_at=self.now)
                             for index, shop_id in enumerate((None, 2, 3))])
            session.add_all([
                ConnectionMonitorTarget(id=10, pg_host_id=41, test_enabled=True, is_public=True, public_name="<b>عمومی</b>", generation="one", endpoint_count=1),
                ConnectionMonitorTarget(id=11, pg_host_id=42, test_enabled=True, is_public=False, public_name="private", generation="one", endpoint_count=1),
                ConnectionMonitorTarget(id=12, pg_host_id=43, test_enabled=False, public_name="paused"),
                ConnectionMonitorTarget(id=20, reseller_id=2, pg_host_id=41, test_enabled=True, is_public=True, public_name="فروشگاه دوم", generation="two", endpoint_count=1),
                ConnectionMonitorTarget(id=30, reseller_id=3, pg_host_id=41, test_enabled=True, is_public=True, public_name="فروشگاه سوم", generation="three", endpoint_count=1),
            ])
            await session.flush()
            session.add_all([ConnectionMonitorSnapshot(
                reseller_id=shop_id, target_id=target_id, endpoint_key="internal-endpoint-key", generation=generation,
                status="healthy", checked_at=self.now, delay_ms=123, destination="gstatic", success_streak=1, has_observation=True,
            ) for shop_id, target_id, generation in ((None, 10, "one"), (2, 20, "two"), (3, 30, "three"))])
            await session.commit()

    async def page(self, shop_id: int | None = None, *, after_id: int = 0) -> PublicConnectionPage:
        scope = set_shop_reseller_id(shop_id)
        try:
            async with self.Session() as session:
                return await public_connection_page(session, now=self.now, after_id=after_id)
        finally:
            reset_shop_reseller_id(scope)

    async def test_only_published_active_entries_appear_and_html_names_are_escaped(self) -> None:
        page = await self.page()
        self.assertEqual(len(page.entries), 1)
        self.assertEqual(page.entries[0].status, "healthy")
        text = public_status_text(page, dict(DEFAULT_SETTINGS), now=self.now)
        self.assertIn("&lt;b&gt;عمومی&lt;/b&gt;", text)
        self.assertIn("بررسی از سرور ربات", text)
        for secret in ("encrypted-sensitive-token", "internal-endpoint-key", "123", "gstatic", "private", "paused", "فروشگاه دوم"):
            self.assertNotIn(secret, text)
        self.assertEqual(set(asdict(page.entries[0])), {"public_name", "status", "checked_at", "probe_label", "is_catalog_stale"})
        self.assertFalse(page.entries[0].is_catalog_stale)
        self.assertNotIn(CATALOG_STALE_NOTICE, text)

    async def test_second_shop_and_second_customer_never_fall_back_to_main_status(self) -> None:
        second = await self.page(2)
        another_customer_same_shop = await self.page(2)
        third = await self.page(3)
        self.assertEqual(second, another_customer_same_shop)
        self.assertEqual([entry.public_name for entry in second.entries], ["فروشگاه دوم"])
        self.assertEqual([entry.public_name for entry in third.entries], ["فروشگاه سوم"])
        self.assertEqual((await self.page(999)).entries, ())
        with self.assertRaises(ValueError):
            await self.page(2, after_id=30)
        with self.assertRaises(ValueError):
            await self.page(after_id=20)

    async def test_expired_evidence_becomes_unknown_at_the_exact_boundary_without_db_writes(self) -> None:
        async with self.Session() as session:
            row = await session.scalar(select(ConnectionMonitorSnapshot).where(ConnectionMonitorSnapshot.target_id == 10))
            row.checked_at = self.now - timedelta(seconds=180)
            await session.commit()
        page = await self.page()
        self.assertEqual(page.entries[0].status, "unknown")
        self.assertIsNotNone(page.entries[0].checked_at)
        text = public_status_text(page, dict(DEFAULT_SETTINGS), now=self.now)
        self.assertIn("نتیجه قدیمی", text)
        self.assertNotIn(CATALOG_STALE_NOTICE, text)
        self.assertFalse(page.entries[0].is_catalog_stale)
        async with self.Session() as session:
            row = await session.scalar(select(ConnectionMonitorSnapshot).where(ConnectionMonitorSnapshot.target_id == 10))
            self.assertEqual((row.status, row.success_streak), ("healthy", 1))

    async def test_missing_endpoint_or_old_generation_cannot_display_a_healthy_host(self) -> None:
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, 10)
            target.endpoint_count = 2
            await session.commit()
        entry = (await self.page()).entries[0]
        self.assertEqual(entry.status, "unknown")
        self.assertIsNone(entry.checked_at)
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, 10)
            target.endpoint_count = 1
            target.generation = "new"
            await session.commit()
        entry = (await self.page()).entries[0]
        self.assertEqual(entry.status, "unknown")
        self.assertIsNone(entry.checked_at)

    async def test_disabled_runtime_or_revoked_owner_hides_publication(self) -> None:
        async with self.Session() as session:
            state = await session.scalar(select(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)))
            state.enabled = False
            await session.commit()
        self.assertEqual((await self.page()).entries, ())
        async with self.Session() as session:
            owner = await session.get(OrgPrincipal, 1)
            owner.status = "disabled"
            await session.commit()
        self.assertEqual((await self.page(2)).entries, ())

    async def test_monitoring_account_reused_by_a_legacy_customer_is_hidden_immediately(self) -> None:
        async with self.Session() as session:
            session.add(UserService(bot_user_id=5, pg_user_id=None, pg_username="MONITOR-0"))
            await session.commit()
        self.assertEqual((await self.page()).entries, ())
        self.assertEqual(len((await self.page(2)).entries), 1)

    async def test_stale_catalog_and_malformed_snapshot_are_unknown_without_leaking_payload(self) -> None:
        async with self.Session() as session:
            state = await session.scalar(select(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)))
            state.catalog_synced_at = self.now - timedelta(seconds=180)
            row = await session.scalar(select(ConnectionMonitorSnapshot).where(ConnectionMonitorSnapshot.target_id == 10))
            row.samples_json = '{"token":"sensitive"}'
            await session.commit()
        page = await self.page()
        self.assertEqual(page.entries[0].status, "unknown")
        self.assertTrue(page.entries[0].is_catalog_stale)
        self.assertNotIn("sensitive", repr(page))
        text = public_status_text(page, dict(DEFAULT_SETTINGS), now=self.now)
        self.assertIn(CATALOG_STALE_NOTICE, text)
        self.assertNotIn("sensitive", text)
        self.assertNotIn("catalog_unavailable", text)

    async def test_first_result_is_unknown_and_wrong_scope_snapshot_is_not_used(self) -> None:
        async with self.Session() as session:
            row = await session.scalar(select(ConnectionMonitorSnapshot).where(ConnectionMonitorSnapshot.target_id == 10))
            row.reseller_id = 2
            await session.commit()
        self.assertEqual((await self.page()).entries[0].status, "unknown")

    async def test_pagination_is_bounded_stable_and_uses_current_shop_cursor(self) -> None:
        async with self.Session() as session:
            session.add_all([ConnectionMonitorTarget(
                id=index, pg_host_id=1000 + index, test_enabled=True, is_public=True, public_name=f"عمومی {index}",
                generation="one", endpoint_count=1, display_order=1,
            ) for index in range(100, 112)])
            await session.commit()
        first = await self.page()
        self.assertEqual(len(first.entries), 10)
        self.assertEqual(first.next_id, 108)
        second = await self.page(after_id=first.next_id)
        self.assertEqual([entry.public_name for entry in second.entries], ["عمومی 109", "عمومی 110", "عمومی 111"])
        self.assertIsNone(second.next_id)

    async def test_public_refresh_has_three_selects_and_zero_network_or_state_changes(self) -> None:
        statements: list[str] = []

        def capture(connection: Connection, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
            statements.append(statement)

        event.listen(self.engine.sync_engine, "before_cursor_execute", capture)
        try:
            with patch("app.services.pasarguard.get_pg") as panel:
                with patch("app.services.xray_probe.run_xray_batch") as core:
                    with patch("httpx.AsyncClient") as http:
                        await self.page()
                        panel.assert_not_called()
                        core.assert_not_called()
                        http.assert_not_called()
        finally:
            event.remove(self.engine.sync_engine, "before_cursor_execute", capture)
        self.assertEqual(len(statements), 3)
        self.assertTrue(all(statement.lstrip().startswith("SELECT") for statement in statements))

    async def test_invalid_scope_and_out_of_range_cursor_fail_closed(self) -> None:
        for invalid in (True, 0, -1, "2", 2147483648):
            with self.subTest(scope=invalid), self.assertRaises(ValueError):
                await self.page(invalid)
        for invalid in (True, -1, "10", 2147483648):
            with self.subTest(cursor=invalid), self.assertRaises(ValueError):
                await self.page(after_id=invalid)
