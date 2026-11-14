"""Which shops a person is a customer of (``bot_user_shops``).

``BotUser.reseller_id`` only records the shop that attributed a person first. A
person who buys from the platform and from a shop is a member of both, so each
side keeps seeing them in lists without owning their other purchases.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import BotUser, BotUserShop
from app.services.shop_scope import ShopScopeError, assert_bot_user_in_scope, resolve_shop_scope_id

logger = logging.getLogger(__name__)


def _membership_shop_clause(shop_id: int | None) -> ColumnElement[bool]:
    return BotUserShop.shop_id.is_(None) if not shop_id else BotUserShop.shop_id == int(shop_id)


def shop_member_clause(shop_id: int | None) -> ColumnElement[bool]:
    """Users who are customers of ``shop_id`` (None = platform): attributed to it or a recorded member."""
    attributed = BotUser.reseller_id.is_(None) if not shop_id else BotUser.reseller_id == int(shop_id)
    members = select(BotUserShop.bot_user_id).where(_membership_shop_clause(shop_id))
    return attributed | BotUser.id.in_(members)


async def is_member(session: AsyncSession, bot_user_id: int, shop_id: int | None) -> bool:
    """True when the person is a recorded customer of the shop (attribution is checked by the caller)."""
    found = await session.scalar(
        select(BotUserShop.id)
        .where(BotUserShop.bot_user_id == int(bot_user_id), _membership_shop_clause(shop_id))
        .limit(1)
    )
    return found is not None


async def ensure_member(session: AsyncSession, bot_user_id: int, shop_id: int | None) -> bool:
    """Record the membership once and say whether this call added it.

    A concurrent insert of the same pair is not an error.
    """
    if await is_member(session, bot_user_id, shop_id):
        return False
    try:
        async with session.begin_nested():
            session.add(BotUserShop(bot_user_id=int(bot_user_id), shop_id=int(shop_id) if shop_id else None))
            await session.flush()
    except IntegrityError:
        logger.debug("membership already recorded user=%s shop=%s", bot_user_id, shop_id)
        return False
    return True


async def assert_customer_in_staff_scope(session: AsyncSession, staff: dict, user: BotUser) -> None:
    """Staff may work with a customer of their shop (attributed or recorded member).

    Account-wide actions (role, block, delete) keep the stricter
    ``assert_bot_user_in_scope``: they affect the person in every shop.
    """
    try:
        assert_bot_user_in_scope(staff, user)
    except ShopScopeError:
        if await is_member(session, int(user.id), resolve_shop_scope_id(staff)):
            return
        raise


async def is_shop_customer(session: AsyncSession, user: BotUser, shop_id: int | None) -> bool:
    """True when the person is attributed to the shop (None = platform) or recorded as one of its customers."""
    if (user.reseller_id or None) == (shop_id or None):
        return True
    return await is_member(session, int(user.id), shop_id)
