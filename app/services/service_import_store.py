"""Open requests to add an existing service, kept while an admin has not decided yet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ServiceImportRequest

REQUEST_TTL = timedelta(days=7)
MAX_OPEN_PER_USER = 3
STATUS_PENDING = "pending"
STATUS_APPROVING = "approving"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"


class TooManyRequests(ValueError):
    """The customer already has the maximum number of requests waiting."""


async def open_request(
    session: AsyncSession, *, user_id: int, shop_id: int | None, panel_user_id: int, panel_username: str
) -> tuple[ServiceImportRequest, bool]:
    """Create the request, or return the one already waiting for this customer and panel user.

    The flag tells whether the request is new, so the admins are told once, not on every repeat.

    Runs inside the caller's transaction (the customer row is already locked there), so the
    per-customer cap holds; the partial unique index backs it up for simultaneous callers.
    """
    now = datetime.now(timezone.utc)
    waiting = await session.scalar(
        select(ServiceImportRequest).where(
            ServiceImportRequest.bot_user_id == int(user_id),
            ServiceImportRequest.panel_user_id == int(panel_user_id),
            ServiceImportRequest.status == STATUS_PENDING,
        )
    )
    if waiting is not None:
        if as_utc(waiting.expires_at) <= now:
            waiting.expires_at = now + REQUEST_TTL
        return waiting, False
    open_count = int(
        await session.scalar(
            select(func.count()).select_from(ServiceImportRequest).where(
                ServiceImportRequest.bot_user_id == int(user_id),
                ServiceImportRequest.status == STATUS_PENDING,
                ServiceImportRequest.expires_at > now,
            )
        )
        or 0
    )
    if open_count >= MAX_OPEN_PER_USER:
        raise TooManyRequests
    request = ServiceImportRequest(
        bot_user_id=int(user_id),
        shop_id=shop_id,
        panel_user_id=int(panel_user_id),
        panel_username=panel_username[:128],
        status=STATUS_PENDING,
        expires_at=now + REQUEST_TTL,
    )
    session.add(request)
    await session.flush()
    return request, True


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
