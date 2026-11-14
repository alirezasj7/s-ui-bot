"""Independent sessions contend for committed runtime and target leases."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import delete, select, update

from connection_monitor_support import MonitorDatabaseCase

from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget
from app.services.connection_monitor_claims import (
    MONITOR_LEASE_SECONDS,
    MonitorCycleClaim,
    claim_monitor_cycle,
    claim_monitor_target,
    release_monitor_cycle,
    release_monitor_target,
)
from app.services.connection_monitor_settings import monitor_settings


class MonitorClaimTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with self.Session() as session:
            session.add_all([
                ConnectionMonitorState(enabled=True, pg_user_id=900, pg_username="monitor-only", subscription_token_enc="synthetic", account_revision="one"),
                ConnectionMonitorState(reseller_id=2, enabled=True, pg_user_id=901, pg_username="shop-monitor",
                                       subscription_token_enc="shop-synthetic", account_revision="shop"),
                ConnectionMonitorTarget(id=10, pg_host_id=41, subscription_key="A" * 43, test_enabled=True, generation="generation-one",
                                        endpoint_count=1, next_check_at=self.now),
                ConnectionMonitorTarget(id=20, reseller_id=2, pg_host_id=41, subscription_key="A" * 43, test_enabled=True,
                                        generation="shop-generation", endpoint_count=1, next_check_at=self.now),
            ])
            await session.commit()

    async def cycle(self, *, later: int = 0) -> MonitorCycleClaim | None:
        async with self.Session() as session:
            result = await claim_monitor_cycle(session, now=self.now + timedelta(seconds=later))
            self.assertFalse(session.in_transaction())
            return result

    async def test_two_sessions_have_one_global_claim_winner(self) -> None:
        start = asyncio.Event()

        async def contend() -> MonitorCycleClaim | None:
            async with self.Session() as session:
                await start.wait()
                return await claim_monitor_cycle(session, now=self.now)

        tasks = [asyncio.create_task(contend()), asyncio.create_task(contend())]
        start.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(sum(item is not None for item in results), 1)
        async with self.Session() as session:
            other = await session.scalar(select(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id == 2))
            self.assertIsNone(other.cycle_token)

    async def test_two_sessions_have_one_target_claim_winner(self) -> None:
        cycle = await self.cycle()
        self.assertIsNotNone(cycle)
        start = asyncio.Event()

        async def contend() -> object:
            async with self.Session() as session:
                await start.wait()
                result = await claim_monitor_target(session, cycle, target_id=10, now=self.now)
                self.assertFalse(session.in_transaction())
                return result

        tasks = [asyncio.create_task(contend()), asyncio.create_task(contend())]
        start.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(sum(item is not None for item in results), 1)

    async def test_expiry_allows_reclaim_and_old_release_cannot_clear_new_tokens(self) -> None:
        old_cycle = await self.cycle()
        async with self.Session() as session:
            old_target = await claim_monitor_target(session, old_cycle, target_id=10, now=self.now)
        new_cycle = await self.cycle(later=MONITOR_LEASE_SECONDS)
        self.assertIsNotNone(new_cycle)
        self.assertNotEqual(old_cycle.token, new_cycle.token)
        async with self.Session() as session:
            new_target = await claim_monitor_target(session, new_cycle, target_id=10, now=self.now + timedelta(seconds=MONITOR_LEASE_SECONDS))
            await release_monitor_target(session, old_target)
            await release_monitor_cycle(session, old_cycle)
        async with self.Session() as session:
            state = await session.scalar(select(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)))
            target = await session.get(ConnectionMonitorTarget, 10)
            self.assertEqual(state.cycle_token, new_cycle.token)
            self.assertEqual(target.claim_token, new_target.token)

    async def test_wrong_shop_target_cannot_be_claimed(self) -> None:
        cycle = await self.cycle()
        async with self.Session() as session:
            self.assertIsNone(await claim_monitor_target(session, cycle, target_id=20, now=self.now))

    async def test_invalidated_cycle_cannot_claim_more_targets(self) -> None:
        for values in ({"enabled": False}, {"account_revision": "new"}, {"cycle_token": "replaced"}):
            async with self.Session() as session:
                await session.execute(update(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)).values(
                    enabled=True, account_revision="one", cycle_token=None, cycle_lease_until=None))
                await session.commit()
            cycle = await self.cycle()
            async with self.Session() as session:
                await session.execute(update(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)).values(**values))
                await session.commit()
                self.assertIsNone(await claim_monitor_target(session, cycle, target_id=10, now=self.now))

    async def test_expired_cycle_is_rejected_at_the_boundary(self) -> None:
        cycle = await self.cycle()
        async with self.Session() as session:
            self.assertIsNone(await claim_monitor_target(session, cycle, target_id=10, now=self.now + timedelta(seconds=MONITOR_LEASE_SECONDS)))

    async def test_paused_unmapped_and_future_due_targets_are_not_claimed(self) -> None:
        cycle = await self.cycle()
        for values in ({"test_enabled": False}, {"generation": ""}, {"endpoint_count": 0},
                       {"next_check_at": self.now + timedelta(seconds=1)}):
            async with self.Session() as session:
                await session.execute(update(ConnectionMonitorTarget).where(ConnectionMonitorTarget.id == 10).values(
                    test_enabled=True, generation="generation-one", endpoint_count=1, next_check_at=self.now))
                await session.execute(update(ConnectionMonitorTarget).where(ConnectionMonitorTarget.id == 10).values(**values))
                await session.commit()
                self.assertIsNone(await claim_monitor_target(session, cycle, target_id=10, now=self.now))

    async def test_wrong_tokens_cannot_release_a_valid_claim(self) -> None:
        cycle = await self.cycle()
        async with self.Session() as session:
            target = await claim_monitor_target(session, cycle, target_id=10, now=self.now)
            await release_monitor_cycle(session, replace(cycle, token="wrong"))
            await release_monitor_target(session, replace(target, token="wrong"))
        self.assertIsNone(await self.cycle())
        async with self.Session() as session:
            self.assertIsNone(await claim_monitor_target(session, cycle, target_id=10, now=self.now))

    async def test_disabled_or_incomplete_runtime_is_not_claimed(self) -> None:
        for values in ({"enabled": False}, {"pg_user_id": None}, {"subscription_token_enc": None}, {"account_revision": ""}):
            async with self.Session() as session:
                await session.execute(update(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)).values(
                    enabled=True, pg_user_id=900, pg_username="monitor-only", subscription_token_enc="synthetic", account_revision="one"))
                await session.execute(update(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)).values(**values))
                await session.commit()
            self.assertIsNone(await self.cycle())

    async def test_initialization_race_keeps_a_single_main_state(self) -> None:
        async with self.Session() as session:
            await session.execute(delete(ConnectionMonitorState).where(ConnectionMonitorState.reseller_id.is_(None)))
            await session.commit()
        start = asyncio.Event()

        async def initialize() -> object:
            async with self.Session() as session:
                await start.wait()
                return await monitor_settings(session, self.access)

        tasks = [asyncio.create_task(initialize()), asyncio.create_task(initialize())]
        start.set()
        first, second = await asyncio.gather(*tasks)
        self.assertEqual(first.id, second.id)

    async def test_naive_clock_is_rejected_instead_of_comparing_local_time(self) -> None:
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await claim_monitor_cycle(session, now=self.now.replace(tzinfo=None))
