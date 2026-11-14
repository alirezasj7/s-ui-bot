"""Duplicate card-receipt detection via Telegram file_unique_id + image sha256."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentReceiptFingerprint
from app.services.users import get_setting

log = logging.getLogger(__name__)

MAX_RECEIPT_BYTES = 8 * 1024 * 1024  # 8 MiB


def normalize_dup_policy(raw: str | None) -> str:
    val = (raw or "warn").strip().lower()
    return "block" if val == "block" else "warn"


async def get_receipt_dup_policy(
    session: AsyncSession, *, reseller_id: int | None = None
) -> str:
    raw = await get_setting(session, "receipt_dup_policy", "warn", reseller_id=reseller_id)
    return normalize_dup_policy(raw)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def find_duplicate_receipts(
    session: AsyncSession,
    *,
    file_unique_id: str | None,
    sha256: str | None,
    exclude_payment_id: int | None = None,
) -> list[PaymentReceiptFingerprint]:
    """Return fingerprints matching another payment (same file id or sha256)."""
    clauses = []
    fid = (file_unique_id or "").strip()
    digest = (sha256 or "").strip().lower()
    if fid:
        clauses.append(PaymentReceiptFingerprint.file_unique_id == fid)
    if digest:
        clauses.append(PaymentReceiptFingerprint.sha256 == digest)
    if not clauses:
        return []
    q = select(PaymentReceiptFingerprint).where(or_(*clauses))
    if exclude_payment_id is not None:
        q = q.where(PaymentReceiptFingerprint.payment_id != int(exclude_payment_id))
    rows = (await session.execute(q.order_by(PaymentReceiptFingerprint.id.asc()))).scalars().all()
    return list(rows)


async def store_receipt_fingerprint(
    session: AsyncSession,
    *,
    payment_id: int,
    file_unique_id: str | None,
    sha256: str | None,
    commit: bool = False,
) -> PaymentReceiptFingerprint:
    row = PaymentReceiptFingerprint(
        payment_id=int(payment_id),
        file_unique_id=(file_unique_id or "").strip() or None,
        sha256=(sha256 or "").strip().lower() or None,
    )
    session.add(row)
    await session.flush()
    if commit:
        await session.commit()
        await session.refresh(row)
    return row


async def download_receipt_sha256(bot: Any, file_id: str) -> str | None:
    """Download Telegram file and hash bytes. Never logs file contents."""
    if not file_id or bot is None:
        return None
    try:
        tg_file = await bot.get_file(file_id)
        path = getattr(tg_file, "file_path", None)
        if not path:
            return None
        buf = await bot.download_file(path)
        if buf is None:
            return None
        data = buf.read() if hasattr(buf, "read") else bytes(buf)
        if not data or len(data) > MAX_RECEIPT_BYTES:
            return None
        return sha256_bytes(data)
    except Exception:
        log.debug("receipt sha256 download failed", exc_info=True)
        return None


def format_dup_warning(matches: list[PaymentReceiptFingerprint]) -> str:
    ids = sorted({int(m.payment_id) for m in matches if m.payment_id})
    if not ids:
        return ""
    shown = ", ".join(f"#{i}" for i in ids[:8])
    extra = f" (+{len(ids) - 8})" if len(ids) > 8 else ""
    return (
        f"⚠️ هشدار رسید تکراری: همین تصویر قبلاً برای پرداخت {shown}{extra} ثبت شده."
    )
