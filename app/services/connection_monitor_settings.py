"""Private monitor settings and encrypted references to an existing panel account."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import Integer, exists, func, insert, literal, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget, UserService
from app.services.connection_monitor_access import (
    MONITOR_ACCESS_DENIED,
    MonitorAccess,
    active_monitor_owner,
    require_monitor_owner,
)
from app.services.db_safe import rollback_quiet
from app.services.connection_monitor_accounts import (
    ACCOUNT_UNAVAILABLE as ACCOUNT_UNAVAILABLE, MonitorAccountError, read_monitor_account, validate_monitor_username,
)
from app.services.secret_box import decrypt_secret, encrypt_secret


LOCAL_PROBE_ID = "local"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    id: int
    enabled: bool
    pg_user_id: int | None
    has_account: bool
    username: str | None = None


async def monitor_settings(session: AsyncSession, access: MonitorAccess) -> MonitorSettings:
    await require_monitor_owner(session, access)
    query = select(ConnectionMonitorState).where(
        ConnectionMonitorState.reseller_id.is_(None), ConnectionMonitorState.probe_id == LOCAL_PROBE_ID,
    ).limit(1)
    state = await session.scalar(query)
    if state is None:
        try:
            async with session.begin_nested():
                await session.execute(insert(ConnectionMonitorState).from_select(
                    ["reseller_id", "probe_id"],
                    select(literal(None, Integer), literal(LOCAL_PROBE_ID)).where(active_monitor_owner(access)),
                ))
        except IntegrityError:
            # Only the competing initial insert is rolled back by the savepoint.
            await rollback_quiet(session)
            logger.debug("Monitor state initialization raced with another request")
        state = await session.scalar(query)
    if state is None:
        raise ValueError(MONITOR_ACCESS_DENIED)
    result = MonitorSettings(state.id, state.enabled, state.pg_user_id, bool(state.subscription_token_enc and state.pg_username), state.pg_username)
    await session.commit()
    return result


async def set_monitor_account(session: AsyncSession, access: MonitorAccess, *, username: str) -> MonitorSettings:
    validate_monitor_username(username)
    settings = await monitor_settings(session, access)
    account = await read_monitor_account(username)
    user_id, token, username = account.user_id, account.token, account.username
    encrypted = await asyncio.to_thread(encrypt_secret, token)
    if not encrypted:
        raise MonitorAccountError("secret_unavailable")
    # This is an exclusion check only: a monitoring account must not be sold or
    # attached to any customer, including a different shop. No customer row leaves DB.
    customer_account = exists(select(UserService.id).where(or_(
        UserService.pg_user_id == user_id, func.lower(UserService.pg_username) == username.lower(),
    )))
    if await session.scalar(select(customer_account)):
        await session.rollback()
        raise MonitorAccountError("customer_account")
    result = await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.id == settings.id, ConnectionMonitorState.reseller_id.is_(None),
        active_monitor_owner(access), ~customer_account,
    ).values(
        pg_user_id=user_id, pg_username=username, subscription_token_enc=encrypted,
        account_revision=hashlib.sha256(f"{user_id}:{token}".encode()).hexdigest(), enabled=False,
        cycle_token=None, cycle_lease_until=None, catalog_synced_at=None,
    ))
    if result.rowcount != 1:
        await rollback_quiet(session)
        try:
            await require_monitor_owner(session, access)
        finally:
            await session.rollback()
        raise MonitorAccountError("account_changed")
    await session.execute(update(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.reseller_id.is_(None),
    ).values(generation="", endpoint_count=0, is_public=False, claim_token=None, claim_until=None))
    await session.commit()
    return MonitorSettings(settings.id, False, user_id, True, username)


async def reveal_monitor_token(encrypted: str | None) -> str:
    """An unreadable reference must stop the check rather than imply a host outage."""
    token = await asyncio.to_thread(decrypt_secret, encrypted)
    if not token:
        raise MonitorAccountError("secret_unavailable")
    return token
