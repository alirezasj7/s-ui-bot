"""Manual requests are scoped queue mutations, never inline network probes."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from connection_monitor_support import MonitorDatabaseCase, monitor_access

from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget
from app.services.connection_monitor_queue import QUEUE_RUNTIME_PENDING, QUEUE_UNAVAILABLE, queue_manual_check


class MonitorQueueTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with self.Session() as session:
            session.add(ConnectionMonitorState(enabled=True, pg_user_id=900, pg_username="monitor-only", subscription_token_enc="synthetic",
                                               account_revision="one", catalog_synced_at=self.now))
            session.add_all([
                ConnectionMonitorTarget(id=10, pg_host_id=41, subscription_key="A" * 43, test_enabled=True, generation="one", endpoint_count=1,
                                        next_check_at=self.now + timedelta(seconds=40)),
                ConnectionMonitorTarget(id=20, reseller_id=2, pg_host_id=41, subscription_key="A" * 43, test_enabled=True, generation="shop", endpoint_count=1),
            ])
            await session.commit()

    async def test_concurrent_taps_enqueue_once_and_commit_the_cooldown(self) -> None:
        async def enqueue() -> bool:
            async with self.Session() as session:
                try:
                    await queue_manual_check(session, self.access, target_id=10, now=self.now)
                    self.assertFalse(session.in_transaction())
                    return True
                except ValueError:
                    return False

        self.assertEqual(sum(await asyncio.gather(enqueue(), enqueue())), 1)
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, 10)
            self.assertTrue(target.manual_pending)
            self.assertIsNotNone(target.manual_available_at)
            self.assertIsNone(target.claim_token)

    async def test_wrong_shop_and_customer_cannot_queue_or_change_a_target(self) -> None:
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await queue_manual_check(session, self.access, target_id=20, now=self.now)
            with self.assertRaises(ValueError):
                await queue_manual_check(session, monitor_access(role="customer", org_principal_id=None), target_id=10, now=self.now)
        async with self.Session() as session:
            targets = (await session.scalars(select(ConnectionMonitorTarget))).all()
            self.assertTrue(all(not target.manual_pending for target in targets))

    async def test_stale_catalog_and_strict_numeric_bounds_reject_requests(self) -> None:
        async with self.Session() as session:
            for target_id in (True, -1, 0, 2147483648, "10"):
                with self.subTest(target_id=target_id), self.assertRaises(ValueError) as ctx:
                    await queue_manual_check(session, self.access, target_id=target_id, now=self.now)
                self.assertEqual(str(ctx.exception), QUEUE_UNAVAILABLE)
            with self.assertRaises(ValueError) as ctx:
                await queue_manual_check(session, self.access, target_id=10, now=self.now + timedelta(seconds=180))
            self.assertEqual(str(ctx.exception), QUEUE_RUNTIME_PENDING)

    async def test_unsynced_catalog_explains_runtime_pending_not_generic_queue_error(self) -> None:
        async with self.Session() as session:
            state = await session.scalar(select(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)))
            state.catalog_synced_at = None
            await session.commit()
        async with self.Session() as session:
            with self.assertRaises(ValueError) as ctx:
                await queue_manual_check(session, self.access, target_id=10, now=self.now)
            self.assertEqual(str(ctx.exception), QUEUE_RUNTIME_PENDING)
            # Catalog freshness covers first sync and later stale panels; do not claim tests just turned on.
            self.assertNotIn("تازه روشن", str(ctx.exception))
            self.assertIn("به‌روز نیست", str(ctx.exception))

    async def test_cooldown_or_missing_target_keeps_generic_queue_unavailable(self) -> None:
        async with self.Session() as session:
            await queue_manual_check(session, self.access, target_id=10, now=self.now)
        async with self.Session() as session:
            with self.assertRaises(ValueError) as ctx:
                await queue_manual_check(session, self.access, target_id=10, now=self.now)
            self.assertEqual(str(ctx.exception), QUEUE_UNAVAILABLE)
            with self.assertRaises(ValueError) as ctx:
                await queue_manual_check(session, self.access, target_id=999, now=self.now)
            self.assertEqual(str(ctx.exception), QUEUE_UNAVAILABLE)
