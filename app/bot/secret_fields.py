"""Secret settings edited in the bot (API keys, webhook secrets): never shown, never left in the chat."""

from __future__ import annotations

SECRET = "secret"
SET_TEXT = "✅ تنظیم شده"
UNSET_TEXT = "— تنظیم نشده"


def is_secret(kind: str | None) -> bool:
    return kind == SECRET


def secret_state(value: str | None) -> str:
    return SET_TEXT if (value or "").strip() else UNSET_TEXT


def secret_prompt(label: str, value: str | None) -> str:
    return (
        f"<b>{label}</b>\nوضعیت فعلی: {secret_state(value)}\n\n"
        "مقدار جدید را بفرستید. برای امنیت، مقدار فعلی نمایش داده نمی‌شود "
        "و پیام شما بلافاصله از چت پاک می‌شود.\nبرای انصراف: انصراف"
    )
