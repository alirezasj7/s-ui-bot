"""Fresh authenticated catalog and dedicated-account evidence from the single panel."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.py_compat import timeout as async_timeout
from app.services.connection_monitor_accounts import MonitorAccountError, panel_account_error, validate_monitor_account
from app.services.connection_monitor_settings import reveal_monitor_token
from app.services.pasarguard import PasarGuardError, get_pg


@dataclass(frozen=True, slots=True)
class MonitorAccount:
    pg_user_id: int
    revision: str
    encrypted_token: str = field(repr=False)
    username: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MonitorCatalog:
    native_configs: list[dict[str, Any]] = field(repr=False)
    checked_at: datetime


async def read_monitor_catalog(account: MonitorAccount) -> MonitorCatalog:
    pg = get_pg()
    token = await reveal_monitor_token(account.encrypted_token)
    try:
        async with async_timeout(10):
            user = await pg.get_user_by_id(account.pg_user_id)
            validated = validate_monitor_account(user, username=account.username)
            revision = hashlib.sha256(f"{validated.user_id}:{token}".encode()).hexdigest()
            if validated.user_id != account.pg_user_id or not secrets.compare_digest(revision, account.revision):
                raise MonitorAccountError("account_changed")
            # Panel URLs contain an issuance timestamp; a new alias does not revoke this token.
            try:
                native = await pg.subscription_xray(token, subscription_url=user["subscription_url"])
            except PasarGuardError as exc:
                if exc.status_code in (401, 404):
                    raise MonitorAccountError("account_changed") from None
                raise
    except (PasarGuardError, httpx.HTTPError, TimeoutError) as exc:
        raise panel_account_error(exc) from None
    return MonitorCatalog(native, datetime.now(timezone.utc))
