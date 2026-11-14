"""Phase D4 — thin cross-channel identity helpers (no ACL widening).

Web Owner credentials (``data/web_admin.json``) and Telegram platform admin
(``ADMIN_IDS`` / ``BotUser.role=admin``) are **independent** stores. Matching
them is an ops concern, not automatic linking (Q1 deferred).

Shop ACL for resellers is already unified via ``authz`` / ``web_permissions``
(C4). ``bot_permissions`` remains a write-only mirror (Q3).

PasarGuard management on Bot stays platform-admin-only; reseller/pg_staff use
Web (Q2). See ``docs/PHASE_D4_IDENTITY_MATRIX.md``.
"""

from __future__ import annotations

from typing import Any, Collection, Iterable


def is_web_platform_admin(staff: dict | None) -> bool:
    """True when the Web session role string is ``admin`` (legacy shop label).

    SAFE LEGACY identity label only — does **not** grant platform-catalog or
    cross-tenant authority. Shop/tenant security paths use
    ``shop_scope.is_platform_admin`` → ``is_explicit_owner_staff`` (Phase 1G).
    Hierarchy-global authority: ``is_explicit_owner_staff`` /
    ``authz.is_explicit_org_owner``.
    """
    if not staff:
        return False
    return (staff.get("role") or "").strip() == "admin"


def is_explicit_owner_staff(staff: dict | None) -> bool:
    """True only for an explicit Org Owner principal on the staff dict.

    ``role=admin`` alone is insufficient. Requires server-attached
    ``org_principal_id`` depth 0 (optionally flagged ``web_owner=True``).
    """
    if not staff:
        return False
    try:
        depth = staff.get("org_depth")
        depth_i = int(depth) if depth is not None else None
    except (TypeError, ValueError):
        return False
    if depth_i != 0:
        return False
    if staff.get("org_parent_id") is not None:
        return False
    status = str(staff.get("org_status") or "").strip() or "active"
    if status != "active":
        return False
    try:
        pid = int(staff.get("org_principal_id") or 0)
    except (TypeError, ValueError):
        return False
    return pid > 0


def is_bot_platform_admin(
    user: Any | None,
    *,
    admin_ids: Collection[int] | None = None,
) -> bool:
    """True when the Telegram user is a platform admin (role or ADMIN_IDS).

    Does **not** consult ``web_admin.json``. Pass ``admin_ids`` from settings
    (or omit to load settings) — thin helper only; behavior matches C4.
    """
    if user is None:
        return False
    role = getattr(user, "role", None)
    if role == "admin":
        return True
    try:
        tid = int(getattr(user, "telegram_id", 0) or 0)
    except (TypeError, ValueError):
        return False
    if tid <= 0:
        return False
    ids = admin_ids
    if ids is None:
        from app.config import get_settings

        ids = get_settings().admin_ids
    return tid in set(ids or ())


def is_synthetic_telegram_id(telegram_id: int | None) -> bool:
    """True for missing or non-positive Telegram ids (internal / provisioned)."""
    try:
        return int(telegram_id or 0) <= 0
    except (TypeError, ValueError):
        return True


def deliverable_telegram_id(telegram_id: int | None) -> int | None:
    """Return a positive Telegram chat id, or None for synthetic/invalid."""
    if is_synthetic_telegram_id(telegram_id):
        return None
    return int(telegram_id)  # type: ignore[arg-type]


def identity_help_fa(role: str | None) -> dict[str, Any]:
    """In-product identity guidance (Q4) keyed by web session role."""
    r = (role or "").strip()
    if r == "admin":
        return {
            "title": "هویت ادمین وب و تلگرام",
            "lines": [
                "ورود وب‌پنل از حساب ادمین وب است؛ ابزارهای ادمین در تلگرام از شناسه‌های ادمین ربات (ADMIN_IDS) — این دو به‌صورت خودکار یکی نیستند.",
                "چک‌لیست مالک: ۱) ورود وب با نقش Owner/Principal مالک ۲) همان انسان در ADMIN_IDS تلگرام ۳) پس از اتصال، منوی Owner فقط با Principal مالک دیده می‌شود (نه فقط role=admin).",
                "مدیریت پاسارگارد در ربات فقط برای ادمین اصلی است. نماینده و ادمین فرعی پاسارگارد را از وب‌پنل مدیریت می‌کنند.",
                "فروشگاه نماینده در وب و ربات از یک مجموعه دسترسی مشترک استفاده می‌کند.",
                "رمز ورود وب‌پنل با رمز اتصال پاسارگارد (در تنظیمات سرور) یکی نیست مگر خودتان عمداً یکی کنید.",
            ],
        }
    if r == "pg_staff":
        return {
            "title": "ادمین فرعی پاسارگارد (فقط وب)",
            "lines": [
                "این حساب فقط وب‌پنل پاسارگارد دارد — فروشگاه و منوی نماینده در ربات برای شما فعال نیست.",
                "نام کاربری وب باید با ادمین پاسارگارد یکی باشد؛ تغییر رمز از همین صفحه رمز پاسارگارد را هم همگام می‌کند (در صورت آماده‌بودن).",
                "اگر منوها محدودند، از ادمین اصلی بخواهید اعتبارنامه را در «ادمین‌ها» تکمیل کند.",
            ],
        }
    if r == "reseller":
        return {
            "title": "نماینده — وب و ربات",
            "lines": [
                "دسترسی فروشگاه در وب‌پنل و ربات فروشگاه یکی است (همان مجوزهای ذخیره‌شده).",
                "مدیریت کاربران/منابع پاسارگارد از وب‌پنل انجام می‌شود؛ ربات فروشگاه ابزارهای پاسارگارد ادمین اصلی را ندارد.",
                "اگر به ادمین پاسارگارد وصل هستید، نام کاربری وب باید همان نام پاسارگارد بماند.",
            ],
        }
    return {
        "title": "هویت حساب",
        "lines": [
            "نقش حساب شما برای این صفحه مشخص نیست — در صورت مشکل با ادمین اصلی تماس بگیرید.",
        ],
    }


def feature_perm_keys(feature_perms: Iterable[tuple[str, str]] | None = None) -> frozenset[str]:
    """Stable set of shop feature keys (for contract tests / menu parity)."""
    if feature_perms is None:
        from app.services.resellers import FEATURE_PERMS

        feature_perms = FEATURE_PERMS
    return frozenset(k for k, _ in feature_perms)
