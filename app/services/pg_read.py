"""Phase C1/C5 — tenant-safe PasarGuard read client selection.

Rules:
- Platform admin/Owner → owner client (`get_pg()`)
- Reseller with shop credentials → `get_pg_for_reseller` (never owner token)
- pg_staff with stored PG password → `get_pg_for_staff` (never owner token)
- pg_staff without credentials → fail closed

Does not change mutation client selection beyond using the same credential rules
(`_staff_pg` / writes mirror this in C2+C5).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pasarguard import (
    PasarGuardClient,
    PasarGuardError,
    get_pg,
    get_pg_for_reseller,
    get_pg_for_staff,
)
from app.services.shop_scope import is_platform_admin, shop_owner_id

# Shown when a restricted principal cannot safely read PG resources.
PG_READ_ISOLATION_MSG = (
    "خواندن امن داده‌های پاسارگارد برای این حساب ممکن نیست "
    "— اعتبارنامه پاسارگارد ذخیره نشده است"
)


class PgReadDenied(Exception):
    """No tenant-safe PG read client for this principal."""

    def __init__(self, message: str = PG_READ_ISOLATION_MSG):
        self.message = message
        super().__init__(message)


def staff_pg_credentials_ready(staff: dict | None) -> bool:
    """True when session advertises stored PG credentials for restricted principals."""
    if not staff:
        return False
    if is_platform_admin(staff):
        return True
    if shop_owner_id(staff) is not None:
        return True
    if staff.get("role") == "principal":
        return bool(staff.get("pg_credentials_ready")) and bool(
            str(staff.get("pg_admin_username") or "").strip()
        )
    return bool(staff.get("pg_credentials_ready"))


async def staff_pg_read_client(
    session: AsyncSession | None,
    staff: dict | None,
) -> PasarGuardClient:
    """Return a PG client allowed for LIST/GET of tenant resources.

    Raises PgReadDenied when the principal must not use the owner token and
    has no own credentials.
    """
    if not staff:
        raise PgReadDenied("نشست نامعتبر است")
    if is_platform_admin(staff):
        return get_pg()

    rid = shop_owner_id(staff)
    if rid:
        if session is None:
            raise PgReadDenied("نشست پایگاه‌داده برای خواندن فروشگاه لازم است")
        try:
            return await get_pg_for_reseller(session, int(rid))
        except PasarGuardError as e:
            raise PgReadDenied(e.user_message(fallback=PG_READ_ISOLATION_MSG)) from e
        except Exception as e:
            raise PgReadDenied(str(e) or PG_READ_ISOLATION_MSG) from e

    if staff.get("role") == "pg_staff":
        if session is None:
            raise PgReadDenied("نشست پایگاه‌داده برای خواندن لازم است")
        try:
            return await get_pg_for_staff(
                session,
                pg_username=staff.get("pg_admin_username"),
                staff_id=staff.get("pg_staff_id"),
            )
        except PasarGuardError as e:
            raise PgReadDenied(e.user_message(fallback=PG_READ_ISOLATION_MSG)) from e
        except Exception as e:
            raise PgReadDenied(str(e) or PG_READ_ISOLATION_MSG) from e

    if staff.get("role") == "principal":
        # Phase 2C: Level-1 Principal — own PG identity only (never Owner token).
        if session is None:
            raise PgReadDenied("نشست پایگاه‌داده برای خواندن لازم است")
        if not str(staff.get("pg_admin_username") or "").strip():
            raise PgReadDenied("هویت پاسارگارد Principal موجود نیست")
        try:
            from app.services.pasarguard import get_pg_for_principal

            return await get_pg_for_principal(
                session,
                principal_id=staff.get("org_principal_id"),
                pg_username=staff.get("pg_admin_username"),
            )
        except PasarGuardError as e:
            raise PgReadDenied(e.user_message(fallback=PG_READ_ISOLATION_MSG)) from e
        except Exception as e:
            raise PgReadDenied(str(e) or PG_READ_ISOLATION_MSG) from e

    raise PgReadDenied(PG_READ_ISOLATION_MSG)


def staff_has_own_pg_read(staff: dict | None) -> bool:
    """True when principal can obtain a non-owner read client."""
    return staff_pg_credentials_ready(staff)


def trust_pg_list_scope(staff: dict | None) -> bool:
    """When True, allow-list None means keep client-scoped results.

    When False (no own client), allow-list None must fail closed.
    """
    if not staff or is_platform_admin(staff):
        return True
    return staff_pg_credentials_ready(staff)


def effective_pg_menu_keys(staff: dict | None) -> list[str]:
    """Menu keys that match what can safely show as data.

    - Admin: full set from staff (caller may expand)
    - Reseller / credentialed pg_staff: mapped pg_permissions
    - pg_staff without credentials: overview only
    """
    if not staff:
        return []
    raw = list(staff.get("pg_permissions") or [])
    if is_platform_admin(staff):
        return raw
    if staff_has_own_pg_read(staff):
        return raw
    return [k for k in raw if k == "pg_overview"]


def empty_pg_read_payload() -> dict[str, Any]:
    return {
        "users": [],
        "templates": [],
        "groups": [],
        "hosts": [],
        "nodes": [],
        "inbounds": [],
        "inbound_tags": [],
        "details": None,
        "read_denied": True,
        "read_denied_msg": PG_READ_ISOLATION_MSG,
    }


async def fetch_own_admin_meta(username: str) -> dict | None:
    """Read-only owner-token lookup of ONE admin by exact username.

    Security invariant:
    - Callers MUST pass the authenticated principal's own PG username.
    - Never use this as a general PG client or to list other admins.
    - Returns None unless the payload username matches (case-insensitive).

    Used when a limited role cannot ``GET /api/admins`` (list) but still needs
    their own quota / role metadata for the web overview — same data they see
    in native PasarGuard about themselves.
    """
    uname = (username or "").strip()
    if not uname:
        return None
    try:
        admin = await get_pg().get_admin(uname)
    except Exception:
        return None
    if not isinstance(admin, dict):
        return None
    got = str(admin.get("username") or "").strip()
    if not got or got.lower() != uname.lower():
        return None
    return admin
