"""The «بزن به کارت» payment screen shared by orders and wallet top-ups."""

from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardButton

from app.services.bbc_settlement import BbcCheckout
from app.services.formatting import format_message, format_toman
from app.services.message_variables import DOMAIN_PAYMENT, render_message_template
from app.services.payment_providers.bezanbecard import format_unique_rial

logger = logging.getLogger(__name__)

TITLE = "💳 بزن به کارت"
PAY_BUTTON = "💳 ورود به صفحهٔ پرداخت"
# The unique amount is Rial and its last digits identify the payment; say so plainly.
RIAL_NOTE = "⚠️ مبلغ بالا به <b>ریال</b> است. دقیقاً همین عدد را واریز کنید، نه رُند شده‌اش."
AUTO_NOTE = "بعد از واریز، تأیید و تحویل خودکار انجام می‌شود."


def checkout_text(
    ui: dict,
    checkout: BbcCheckout,
    *,
    amount_toman: int,
    currency: str,
    order_id: int,
    payment_id: int,
) -> str:
    amount = format_toman(amount_toman, currency)
    unique = format_unique_rial(checkout.unique_amount_rial)
    fallback = f"مبلغ: <b>{amount}</b>\nمبلغ دقیق واریز: <b>{unique}</b>"
    try:
        body = render_message_template(
            ui.get("bbc_pay_text") or "",
            domain=DOMAIN_PAYMENT,
            amount=amount,
            unique_amount=unique,
            order_id=order_id,
            payment_id=payment_id,
            shop_title=ui.get("shop_title") or "",
        )
    except ValueError:
        logger.warning("bbc_pay_text could not be rendered; using the built-in text", exc_info=True)
        body = ""
    return format_message(TITLE, f"{body.strip() or fallback}\n\n{RIAL_NOTE}\n{AUTO_NOTE}\n\n(پرداخت #{payment_id})")


def checkout_rows(checkout: BbcCheckout) -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(text=PAY_BUTTON, url=checkout.payment_url)]]
