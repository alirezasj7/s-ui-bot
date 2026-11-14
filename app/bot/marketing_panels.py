"""Text and keyboards for the admin gift-code and campaign panels (pure, no I/O besides the panel URL)."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Mapping, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot import keyboards as kb
from app.bot.keyboards import _ikb, _style
from app.db.models import ChargeCode, TargetedCampaign
from app.services.campaigns import AUDIENCES
from app.services.formatting import format_number, format_toman

logger = logging.getLogger(__name__)

MARKETING_HUB_CALLBACK = "nv:adm:marketing"
GIFT_PANEL_CALLBACK = "nv:adm:gc"
CAMPAIGN_PANEL_CALLBACK = "nv:adm:cmp"
GIFT_SET_PATTERN = re.compile(r"^adm:gc:set:(\d{1,9}):([01])\Z")
CAMPAIGN_ACTION_PATTERN = re.compile(r"^adm:cmp:(start|pause):(\d{1,9})\Z")

WEB_BUTTON_LABEL = "🌐 مدیریت کامل در وب‌پنل"

CAMPAIGN_STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "running": "در حال ارسال",
    "paused": "متوقف",
    "completed": "تکمیل‌شده",
    "review": "نیازمند بررسی",
}
PRICE_ANNOUNCEMENT_AUDIENCE = "catalog_discount"
PRICE_ANNOUNCEMENT_LABEL = "اطلاع‌رسانی تغییر قیمت"


def panel_page_url(path: str) -> str | None:
    """Absolute panel URL for a Telegram URL button, or ``None`` when no public base is configured."""
    from app.services.setup_wizard import default_panel_base_url

    try:
        base = (default_panel_base_url() or "").rstrip("/")
    except Exception:  # best effort: the panel works without the shortcut button
        logger.warning("panel base url unavailable", exc_info=True)
        return None
    return f"{base}{path}" if base.startswith("http") else None


def _footer_rows(ui: Mapping | None, web_url: str | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if web_url:
        rows.append([_ikb(WEB_BUTTON_LABEL, url=web_url, ui=dict(ui or {}))])
    rows.append([kb.back_button(dict(ui or {}), MARKETING_HUB_CALLBACK)])
    return rows


def _gift_amount(code: ChargeCode) -> str:
    if code.kind == "discount":
        return f"تخفیف {format_number(int(code.percent or 0))}٪"
    return f"شارژ {format_toman(int(code.amount or 0))}"


def gift_codes_panel(
    codes: Sequence[ChargeCode],
    details: Mapping[int, Mapping[str, str]],
    *,
    ui: Mapping | None = None,
    web_url: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["🎁 <b>کدهای هدیه</b>", "با دکمه‌ی هر کد، آن را روشن یا خاموش کنید.", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for code in codes:
        state = details.get(code.id, {}).get("state") or ("فعال" if code.is_active else "خاموش")
        uses = f"{code.used_count}/{code.max_uses}" if code.max_uses is not None else str(code.used_count)
        lines.append(
            f"<code>{html.escape(code.code)}</code> — {_gift_amount(code)} — {html.escape(state)} — مصرف {uses}"
        )
        target = 0 if code.is_active else 1
        icon = "⏸ خاموش" if code.is_active else "▶️ روشن"
        rows.append(
            [
                _ikb(
                    f"{icon}: {code.code}",
                    callback_data=f"adm:gc:set:{code.id}:{target}",
                    ui=ui,
                    style=_style(dict(ui or {}), "reject" if code.is_active else "confirm"),
                )
            ]
        )
    if not codes:
        lines.append("هنوز کدی ساخته نشده. ساخت کد از وب‌پنل انجام می‌شود.")
    rows.extend(_footer_rows(ui, web_url))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _campaign_title(campaign: TargetedCampaign) -> str:
    if campaign.audience == PRICE_ANNOUNCEMENT_AUDIENCE:
        return PRICE_ANNOUNCEMENT_LABEL
    return AUDIENCES.get(campaign.audience, "کمپین")


def campaigns_panel(
    campaigns: Sequence[TargetedCampaign],
    progress: Mapping[int, Mapping[str, int]],
    *,
    ui: Mapping | None = None,
    web_url: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["📣 <b>کمپین‌های هدفمند</b>", "وضعیت آخرین کمپین‌ها؛ ساخت کمپین از وب‌پنل انجام می‌شود.", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for campaign in campaigns:
        counts = progress.get(campaign.id, {})
        total = sum(counts.values())
        status = CAMPAIGN_STATUS_LABELS.get(campaign.status, "نامشخص")
        lines.append(
            f"#{campaign.id} — {html.escape(_campaign_title(campaign))} — {status}"
            f" — {format_number(counts.get('sent', 0))}/{format_number(total)} ارسال‌شده"
        )
        if campaign.status in {"draft", "paused"}:
            rows.append(
                [
                    _ikb(
                        f"▶️ شروع/ادامه #{campaign.id}",
                        callback_data=f"adm:cmp:start:{campaign.id}",
                        ui=ui,
                        style=_style(dict(ui or {}), "confirm"),
                    )
                ]
            )
        elif campaign.status == "running":
            rows.append(
                [
                    _ikb(
                        f"⏸ توقف #{campaign.id}",
                        callback_data=f"adm:cmp:pause:{campaign.id}",
                        ui=ui,
                        style=_style(dict(ui or {}), "reject"),
                    )
                ]
            )
    if not campaigns:
        lines.append("هنوز کمپینی ساخته نشده.")
    rows.extend(_footer_rows(ui, web_url))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)
