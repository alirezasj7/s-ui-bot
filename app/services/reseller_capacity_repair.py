"""Re-read the existing limits of resellers granted with «ظرفیت فعلی» whose capacity was saved as zero.

Before the grant checked its reads, a PasarGuard read that failed (or a limit below 1 GB) was
stored as 0 GB / 0 users, which the panel shows as unlimited. Only rows with both values at zero
are touched, and a row is changed only when the admin's live limits are readable and non-zero.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PgAdminSubscription, ResellerPlan
from app.services.pg_admin_subscription import (
    PLAN_KIND_CURRENT_CAPACITY,
    STATUS_ACTIVE,
    PgCapacityUnreadable,
    read_live_pg_admin_capacity,
)

logger = logging.getLogger(__name__)

REPAIR_BATCH = 200
READ_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class RepairReport:
    fixed: int = 0
    unreadable: int = 0
    unlimited: int = 0


async def _read(username: str, gate: asyncio.Semaphore) -> tuple[int, int] | None:
    async with gate:
        try:
            return await read_live_pg_admin_capacity(username)
        except PgCapacityUnreadable:
            return None


async def repair_current_capacity_snapshots(session: AsyncSession) -> RepairReport:
    """Fix up to ``REPAIR_BATCH`` zero snapshots; run again for more. Panel reads are bounded."""
    rows = (
        await session.execute(
            select(PgAdminSubscription.id, PgAdminSubscription.pg_username)
            .join(ResellerPlan, ResellerPlan.id == PgAdminSubscription.plan_id)
            .where(
                ResellerPlan.plan_kind == PLAN_KIND_CURRENT_CAPACITY,
                PgAdminSubscription.access_status == STATUS_ACTIVE,
                PgAdminSubscription.base_gb == 0,
                PgAdminSubscription.base_users == 0,
            )
            .order_by(PgAdminSubscription.id)
            .limit(REPAIR_BATCH)
        )
    ).all()
    gate = asyncio.Semaphore(READ_CONCURRENCY)
    live = await asyncio.gather(*(_read(name, gate) for _id, name in rows))
    fixed = unreadable = unlimited = 0
    for (sub_id, _name), capacity in zip(rows, live, strict=True):
        if capacity is None:
            unreadable += 1
        elif capacity == (0, 0):
            unlimited += 1
        else:
            # The zero check repeats in SQL so a row changed meanwhile is left alone.
            result = await session.execute(
                update(PgAdminSubscription)
                .where(
                    PgAdminSubscription.id == sub_id,
                    PgAdminSubscription.base_gb == 0,
                    PgAdminSubscription.base_users == 0,
                )
                .values(base_gb=capacity[0], base_users=capacity[1]),
                execution_options={"synchronize_session": False},
            )
            fixed += int(result.rowcount or 0)
    await session.commit()
    logger.info("current capacity repair fixed=%s unreadable=%s unlimited=%s", fixed, unreadable, unlimited)
    return RepairReport(fixed=fixed, unreadable=unreadable, unlimited=unlimited)
