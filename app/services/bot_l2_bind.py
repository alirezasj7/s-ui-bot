"""Phase 5B — bind / unbind a Telegram user to an existing depth-2 OrgPrincipal.

Server-side only. Never trusts client principal/parent/depth/bot_user_id/role.
Does not provision Principals, PG admins, bot tokens, or Bot UI.
Unbind clears ``OrgPrincipal.bot_user_id`` only — it does not delete BotUser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, OrgPrincipal
from app.services.org_principals import (
    DEPTH_ONE,
    DEPTH_TWO,
    STATUS_ACTIVE,
    get_principal,
    is_owner_principal,
    list_principals_for_bot_user,
    resolve_org_principal_for_staff,
)
from app.services.org_scope import visible_principal_ids


class L2BotBindError(Exception):
    """Denied or failed L2 Telegram bind."""

    def __init__(self, message: str, *, code: str = "denied"):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class L2BotBindResult:
    principal: OrgPrincipal
    bot_user_id: int
    telegram_id: int
    created_binding: bool


@dataclass(frozen=True)
class L2BotUnbindResult:
    principal: OrgPrincipal
    telegram_id: int | None
    cleared: bool


def _positive_int(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _admin_ids_set(admin_ids: frozenset[int] | set[int] | None) -> frozenset[int]:
    if admin_ids is not None:
        return frozenset(int(x) for x in admin_ids)
    try:
        from app.config import get_settings

        return frozenset(int(x) for x in (get_settings().admin_ids or ()))
    except Exception:
        return frozenset()


async def _load_valid_l2(
    session: AsyncSession, target_principal_id: int
) -> OrgPrincipal:
    pid = _positive_int(target_principal_id)
    if pid <= 0:
        raise L2BotBindError("Principal یافت نشد", code="principal_missing")
    target = await get_principal(session, pid)
    if target is None:
        raise L2BotBindError("Principal یافت نشد", code="principal_missing")
    if is_owner_principal(target):
        raise L2BotBindError(
            "نمی‌توان مالک را به هویت سطح ۲ متصل کرد",
            code="cannot_bind_owner",
        )
    if str(target.status) != STATUS_ACTIVE:
        raise L2BotBindError("Principal غیرفعال است", code="principal_disabled")
    try:
        depth = int(target.depth)
    except (TypeError, ValueError) as exc:
        raise L2BotBindError("عمق Principal نامعتبر است", code="not_level2") from exc
    if depth != DEPTH_TWO:
        raise L2BotBindError(
            "فقط Principal سطح ۲ می‌تواند به تلگرام متصل شود",
            code="not_level2",
        )
    parent_id = _positive_int(target.parent_id)
    if parent_id <= 0:
        raise L2BotBindError("والد سطح ۱ نامعتبر است", code="parent_missing")
    parent = await get_principal(session, parent_id)
    if (
        parent is None
        or str(parent.status) != STATUS_ACTIVE
        or int(getattr(parent, "depth", -1) or -1) != DEPTH_ONE
    ):
        raise L2BotBindError(
            "والد Principal سطح ۲ غیرفعال است",
            code="parent_disabled",
        )
    return target


async def _authorize_binder(
    session: AsyncSession,
    staff: Mapping[str, Any] | None,
    target: OrgPrincipal,
) -> OrgPrincipal:
    actor = await resolve_org_principal_for_staff(session, dict(staff) if staff else None)
    if actor is None or str(actor.status) != STATUS_ACTIVE:
        raise L2BotBindError("احراز هویت نشده", code="unauthenticated")
    if is_owner_principal(actor):
        visible = await visible_principal_ids(session, actor)
        if int(target.id) not in visible:
            raise L2BotBindError(
                "این Principal در محدوده مالک نیست",
                code="out_of_scope",
            )
        return actor
    try:
        depth = int(actor.depth)
    except (TypeError, ValueError):
        depth = -1
    if depth != DEPTH_ONE:
        raise L2BotBindError(
            "فقط مالک یا والد سطح ۱ می‌تواند هویت تلگرام سطح ۲ را متصل کند",
            code="not_authorized",
        )
    if int(target.parent_id or 0) != int(actor.id):
        raise L2BotBindError(
            "فقط فرزند مستقیم خود را می‌توانید متصل کنید",
            code="not_direct_child",
        )
    return actor


async def _bot_user_from_telegram(
    session: AsyncSession, telegram_id: int
) -> BotUser:
    tid = _positive_int(telegram_id)
    if tid <= 0:
        raise L2BotBindError("شناسه تلگرام نامعتبر است", code="telegram_invalid")
    from sqlalchemy import select

    user = (
        await session.execute(select(BotUser).where(BotUser.telegram_id == tid))
    ).scalar_one_or_none()
    if user is None:
        raise L2BotBindError(
            "کاربر تلگرام یافت نشد — ابتدا ربات اصلی را استارت کنید",
            code="bot_user_missing",
        )
    return user


async def bind_l2_bot_telegram(
    session: AsyncSession,
    *,
    staff: Mapping[str, Any] | None,
    target_principal_id: int,
    telegram_id: int,
    admin_ids: frozenset[int] | set[int] | None = None,
    bot_user_id: Any = None,
    parent_id: Any = None,
    depth: Any = None,
    pg_username: Any = None,
    web_owner: Any = None,
    role: Any = None,
) -> L2BotBindResult:
    """Bind ``telegram_id`` to an existing L2 Principal.

    Lookup key ``target_principal_id`` is loaded server-side and re-validated.
    Client hierarchy / ``bot_user_id`` / role fields are ignored.
    """
    _ = bot_user_id, parent_id, depth, pg_username, web_owner, role

    target = await _load_valid_l2(session, target_principal_id)
    await _authorize_binder(session, staff, target)

    user = await _bot_user_from_telegram(session, telegram_id)
    tid = int(user.telegram_id)
    if tid in _admin_ids_set(admin_ids):
        raise L2BotBindError(
            "شناسه تلگرام مالک قابل اتصال به سطح ۲ نیست",
            code="admin_ids_collision",
        )

    from app.services.resellers import get_reseller_profile

    profile = await get_reseller_profile(session, int(user.id))
    if profile is not None and bool(profile.is_active):
        raise L2BotBindError(
            "این کاربر تلگرام نماینده است و به سطح ۲ متصل نمی‌شود",
            code="reseller_collision",
        )

    claimed = await list_principals_for_bot_user(session, int(user.id))
    if len(claimed) > 1:
        raise L2BotBindError(
            "اتصال تلگرام مبهم است",
            code="duplicate_bot_user_id",
        )
    if len(claimed) == 1 and int(claimed[0].id) != int(target.id):
        raise L2BotBindError(
            "این کاربر تلگرام به Principal دیگری متصل است",
            code="binding_collision",
        )

    existing_uid = _positive_int(target.bot_user_id)
    if existing_uid and existing_uid != int(user.id):
        raise L2BotBindError(
            "این Principal قبلاً به کاربر دیگری متصل است",
            code="already_bound",
        )

    if existing_uid == int(user.id):
        return L2BotBindResult(
            principal=target,
            bot_user_id=int(user.id),
            telegram_id=tid,
            created_binding=False,
        )

    target.bot_user_id = int(user.id)
    await session.flush()
    return L2BotBindResult(
        principal=target,
        bot_user_id=int(user.id),
        telegram_id=tid,
        created_binding=True,
    )


async def unbind_l2_bot_telegram(
    session: AsyncSession,
    *,
    staff: Mapping[str, Any] | None,
    target_principal_id: int,
    bot_user_id: Any = None,
    parent_id: Any = None,
    depth: Any = None,
    pg_username: Any = None,
    web_owner: Any = None,
    role: Any = None,
    telegram_id: Any = None,
) -> L2BotUnbindResult:
    """Clear ``OrgPrincipal.bot_user_id`` for an in-scope L2. Does not delete BotUser."""
    _ = bot_user_id, parent_id, depth, pg_username, web_owner, role, telegram_id

    target = await _load_valid_l2(session, target_principal_id)
    await _authorize_binder(session, staff, target)

    existing_uid = _positive_int(target.bot_user_id)
    if not existing_uid:
        return L2BotUnbindResult(
            principal=target,
            telegram_id=None,
            cleared=False,
        )

    user = await session.get(BotUser, existing_uid)
    tid = None
    if user is not None:
        try:
            tid = int(user.telegram_id)
        except (TypeError, ValueError):
            tid = None

    target.bot_user_id = None
    await session.flush()
    return L2BotUnbindResult(
        principal=target,
        telegram_id=tid,
        cleared=True,
    )
