"""Take orders off the failed-delivery list without delivering them again."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeliveryFailure, Order
from app.services.shop_scope import ShopScopeError, assert_order_retry_in_scope

logger = logging.getLogger(__name__)

ORDER_NOT_FOUND = "سفارش پیدا نشد"
NOTHING_TO_DISMISS = "این سفارش در لیست تحویل ناموفق نیست"


async def dismiss_delivery_failures(session: AsyncSession, staff: dict, order_ids: list[int]) -> tuple[int, int]:
    """Resolve every open failure of the given orders in the staff member's own shop.

    Returns ``(dismissed, skipped)``. An order of another shop, a missing order and an order
    without an open failure are skipped; resolving twice is harmless. Nothing is sent and the
    order itself is not changed, so a paid order without a service still shows up as stuck.
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return 0, 0
    orders = (await session.scalars(select(Order).where(Order.id.in_(ids)))).all()
    allowed: list[int] = []
    for order in orders:
        try:
            assert_order_retry_in_scope(staff, order)
        except ShopScopeError:
            continue
        allowed.append(int(order.id))
    if not allowed:
        return 0, len(ids)
    with_open = set(
        (
            await session.scalars(
                select(DeliveryFailure.order_id)
                .where(DeliveryFailure.order_id.in_(allowed), DeliveryFailure.resolved_at.is_(None))
                .distinct()
            )
        ).all()
    )
    if with_open:
        await session.execute(
            update(DeliveryFailure)
            .where(DeliveryFailure.order_id.in_(with_open), DeliveryFailure.resolved_at.is_(None))
            .values(resolved_at=datetime.now(timezone.utc)),
            execution_options={"synchronize_session": False},
        )
        await session.commit()
        logger.info("delivery failures dismissed orders=%s by=%s", sorted(with_open), staff.get("role"))
    return len(with_open), len(ids) - len(with_open)
