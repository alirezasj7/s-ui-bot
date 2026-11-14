"""Explicit main-bot Owner authorization for private monitoring configuration."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import OrgPrincipal
from app.services.authz import AuthzContext, can_shop, is_explicit_org_owner


MONITOR_VIEW_PERMISSION = "connection_status"
MONITOR_MANAGE_PERMISSION = "connection_status_manage"
MONITOR_ACCESS_DENIED = "دسترسی به مدیریت وضعیت اتصال مجاز نیست."


@dataclass(frozen=True, slots=True)
class MonitorAccess:
    authz: AuthzContext
    is_main_bot: bool


def active_monitor_owner(access: MonitorAccess) -> ColumnElement[bool]:
    """Repeat the live principal check in the mutation statement itself."""
    return exists(select(OrgPrincipal.id).where(
        OrgPrincipal.id == access.authz.principal_id,
        OrgPrincipal.depth == 0,
        OrgPrincipal.parent_id.is_(None),
        OrgPrincipal.status == "active",
    ))


async def require_monitor_owner(session: AsyncSession, access: MonitorAccess) -> None:
    ctx = access.authz
    if access.is_main_bot is not True or not is_explicit_org_owner(ctx):
        raise ValueError(MONITOR_ACCESS_DENIED)
    if type(ctx.principal_id) is not int or not 1 <= ctx.principal_id <= 2147483647:
        raise ValueError(MONITOR_ACCESS_DENIED)
    if not can_shop(ctx, MONITOR_VIEW_PERMISSION) or not can_shop(ctx, MONITOR_MANAGE_PERMISSION):
        raise ValueError(MONITOR_ACCESS_DENIED)
    if not await session.scalar(select(active_monitor_owner(access))):
        raise ValueError(MONITOR_ACCESS_DENIED)
