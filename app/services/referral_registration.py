"""Referral validation and prompts for new bot registrations."""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser


class ReferralRequired(ValueError):
    def __init__(self, ui: dict[str, str], *, invalid: bool = False):
        super().__init__("A valid referral is required to register")
        self.ui = ui
        self.invalid = invalid


def normalize_referral_code(raw: str | None) -> str:
    code = (raw or "").strip()
    if code.lower().startswith("ref_"):
        code = code[4:]
    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", code):
        return ""
    return code.upper()


async def find_registration_referrer(
    session: AsyncSession,
    raw_code: str | None,
    *,
    telegram_id: int,
    reseller_owner_id: int | None,
) -> BotUser | None:
    code = normalize_referral_code(raw_code)
    if not code:
        return None
    scope_filter = (
        or_(BotUser.reseller_id == reseller_owner_id, BotUser.id == reseller_owner_id)
        if reseller_owner_id
        else BotUser.reseller_id.is_(None)
    )
    return await session.scalar(
        select(BotUser).where(
            BotUser.referral_code == code,
            BotUser.telegram_id != telegram_id,
            BotUser.is_blocked.is_(False),
            scope_filter,
        )
    )


def referral_required_outbound(ui: dict[str, str], *, invalid: bool = False) -> tuple[str, dict]:
    from app.services.rich_text import outbound_setting_text, rich_plain_text
    from app.services.users import DEFAULT_SETTINGS

    raw = ui.get("referral_required_text") or ""
    if not rich_plain_text(raw).strip():
        raw = DEFAULT_SETTINGS["referral_required_text"]
    append = "\n\nکد معرف معتبر نیست. کد معتبر همین فروشگاه را ارسال کنید." if invalid else ""
    return outbound_setting_text(raw, append=append)
