"""Safe connection-settings errors shared by Telegram and web interfaces."""

from __future__ import annotations

from app.services.connection_monitor_access import MONITOR_ACCESS_DENIED
from app.services.connection_monitor_accounts import ACCOUNT_MESSAGES, ACCOUNT_UNAVAILABLE, MonitorAccountError
from app.services.connection_monitor_actions import INVALID_PREFERENCES
from app.services.connection_monitor_preferences import PREFERENCES_UNAVAILABLE
from app.services.connection_monitor_queue import QUEUE_RUNTIME_PENDING, QUEUE_UNAVAILABLE
from app.services.connection_monitor_types import MonitorConfigError
from app.services.connection_status_texts import REASON_LABELS
from app.services.xray_probe_resources import XrayProbeError


MONITOR_FAILED = "تست اتصال انجام نشد؛ کمی بعد دوباره تلاش کنید."
SAFE_ERRORS = frozenset({
    MONITOR_ACCESS_DENIED, ACCOUNT_UNAVAILABLE, INVALID_PREFERENCES, PREFERENCES_UNAVAILABLE,
    QUEUE_UNAVAILABLE, QUEUE_RUNTIME_PENDING,
    "هاست تست یافت نشد.", "صفحه نامعتبر است.", "درخواست نامعتبر است.", "شناسه نامعتبر است.",
})
CORE_MESSAGES = {
    "core_binary": "فایل Xray آماده نیست؛ مسیر CONNECTION_MONITOR_XRAY_PATH و دسترسی فایل و پوشه را بررسی کنید.",
    "core_checksum": "مقدار SHA-256 فایل Xray معتبر نیست؛ تنظیم CONNECTION_MONITOR_XRAY_SHA256 را بررسی کنید.",
}


def monitor_error_message(error: Exception) -> str:
    if isinstance(error, MonitorAccountError):
        return ACCOUNT_MESSAGES.get(error.code, MONITOR_FAILED)
    if isinstance(error, XrayProbeError):
        return CORE_MESSAGES.get(str(error), "اجرای Xray ممکن نشد؛ تنظیمات سرور را بررسی کنید.")
    if isinstance(error, MonitorConfigError):
        return REASON_LABELS.get(error.issue, MONITOR_FAILED)
    if type(error) is ValueError and str(error) in SAFE_ERRORS:
        return str(error)
    return MONITOR_FAILED
