"""Manage test customers and exclude their history from business reporting."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import BotUser
from app.services.authz import authz_from_staff, can_shop
from app.services.shop_scope import resolve_shop_scope_id

DEMO_USERS_PERMISSION = "demo_users"
MAX_BOT_USER_ID = 2**31 - 1


def non_demo_customer(user_id: ColumnElement[int]) -> ColumnElement[bool]:
    """Keep historical rows; evaluate the customer's current reporting status."""
    customer = aliased(BotUser)
    return ~select(customer.id).where(
        customer.id == user_id, customer.is_demo.is_(True),
    ).exists()


async def set_demo_user(
    session: AsyncSession,
    staff: dict[str, Any],
    user_id: int,
    *,
    is_demo: bool,
) -> None:
    """Apply a desired state atomically within the authenticated staff's shop."""
    if not can_shop(authz_from_staff(staff), DEMO_USERS_PERMISSION):
        raise PermissionError("دسترسی به مدیریت کاربران دمو ندارید")
    shop_id = resolve_shop_scope_id(staff)
    if type(user_id) is not int or not 0 < user_id <= MAX_BOT_USER_ID or type(is_demo) is not bool:
        raise ValueError("وضعیت کاربر دمو نامعتبر است")
    scope = BotUser.reseller_id.is_(None) if shop_id is None else BotUser.reseller_id == shop_id
    result = await session.execute(
        update(BotUser).where(BotUser.id == user_id, scope).values(is_demo=is_demo)
    )
    if result.rowcount != 1:
        raise ValueError("کاربر در این فروشگاه یافت نشد")
    await session.commit()
