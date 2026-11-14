"""Internal web-panel tickets: reseller / pg_staff ↔ platform admin."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import DATA_DIR
from app.db.models import (
    PanelTicket,
    PanelTicketMessage,
    PanelTicketPriority,
    PanelTicketStatus,
)

STATUS_LABELS = {
    PanelTicketStatus.OPEN.value: "باز",
    PanelTicketStatus.IN_PROGRESS.value: "در حال بررسی",
    PanelTicketStatus.ANSWERED.value: "پاسخ‌داده‌شده",
    PanelTicketStatus.CLOSED.value: "بسته",
}

PRIORITY_LABELS = {
    PanelTicketPriority.LOW.value: "کم",
    PanelTicketPriority.NORMAL.value: "عادی",
    PanelTicketPriority.HIGH.value: "بالا",
    PanelTicketPriority.URGENT.value: "فوری",
}

STATUS_BADGE = {
    PanelTicketStatus.OPEN.value: "open",
    PanelTicketStatus.IN_PROGRESS.value: "info",
    PanelTicketStatus.ANSWERED.value: "answered",
    PanelTicketStatus.CLOSED.value: "neutral",
}

PRIORITY_BADGE = {
    PanelTicketPriority.LOW.value: "neutral",
    PanelTicketPriority.NORMAL.value: "info",
    PanelTicketPriority.HIGH.value: "warn",
    PanelTicketPriority.URGENT.value: "danger",
}

# Attachments: images, docs, archives — keep modest for panel use
MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024
ALLOWED_ATTACHMENT_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".txt",
    ".zip",
    ".rar",
    ".7z",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".log",
}
_SAFE_NAME_RE = re.compile(r"[^\w.\-()+ ]+", re.UNICODE)

# JSON/poll endpoints that never render the sidebar — skip unread COUNT.
SKIP_UNREAD_PATHS = frozenset(
    {
        "/home/metrics",
        "/home/body",
        "/dashboard/metrics",
        "/pg/metrics",
        "/pg/body",
        "/update/status",
        "/settings/ssl/progress",
        "/backup/status",
        "/tickets",  # derived from list_tickets via unread_from_tickets
    }
)


def should_skip_unread_count(path: str, method: str = "GET") -> bool:
    """True when this request will not render the sidebar HTML."""
    m = (method or "GET").upper()
    if m != "GET":
        return True
    p = path or ""
    if p in SKIP_UNREAD_PATHS:
        return True
    # Dynamic JSON routes (path params) — no sidebar
    if p.startswith("/pg/users/") and p.endswith("/link"):
        return True
    return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_priority(raw: str | None) -> str:
    v = (raw or PanelTicketPriority.NORMAL.value).strip().lower()
    if v in PRIORITY_LABELS:
        return v
    return PanelTicketPriority.NORMAL.value


def normalize_status(raw: str | None) -> str | None:
    v = (raw or "").strip().lower()
    if v in STATUS_LABELS:
        return v
    return None


def actor_from_staff(staff: dict) -> dict[str, Any]:
    """Resolve panel principal for ticket actions."""
    role = staff.get("role") or ""
    if role == "admin":
        return {
            "role": "admin",
            "label": staff.get("username") or "مدیر",
            "reseller_user_id": None,
            "pg_staff_id": None,
            "is_owner": True,
            "is_opener": False,
        }
    if role == "reseller":
        rid = staff.get("bot_user_id")
        return {
            "role": "reseller",
            "label": staff.get("username") or f"نماینده #{rid or '—'}",
            "reseller_user_id": int(rid) if rid else None,
            "pg_staff_id": None,
            "is_owner": False,
            "is_opener": True,
        }
    if role == "pg_staff":
        sid = staff.get("pg_staff_id")
        return {
            "role": "pg_staff",
            "label": staff.get("username") or staff.get("pg_admin_username") or f"ادمین فرعی #{sid or '—'}",
            "reseller_user_id": None,
            "pg_staff_id": int(sid) if sid else None,
            "is_owner": False,
            "is_opener": True,
        }
    raise PermissionError("نقش برای تیکت پنل مجاز نیست")


def can_access_panel_tickets(staff: dict) -> bool:
    return staff.get("role") in {"admin", "reseller", "pg_staff"}


def _scope_query(actor: dict) -> Select[tuple[PanelTicket]]:
    """List/detail scope without messages — callers add selectinload when needed."""
    q = select(PanelTicket)
    if actor["is_owner"]:
        return q.order_by(PanelTicket.updated_at.desc(), PanelTicket.id.desc())
    if actor["role"] == "reseller" and actor["reseller_user_id"]:
        return q.where(PanelTicket.opener_reseller_user_id == int(actor["reseller_user_id"])).order_by(
            PanelTicket.updated_at.desc(), PanelTicket.id.desc()
        )
    if actor["role"] == "pg_staff" and actor["pg_staff_id"]:
        return q.where(PanelTicket.opener_pg_staff_id == int(actor["pg_staff_id"])).order_by(
            PanelTicket.updated_at.desc(), PanelTicket.id.desc()
        )
    return q.where(PanelTicket.id == -1)


def _tickets_upload_dir() -> Path:
    """Private attachment store — never under the public /media/uploads mount."""
    d = DATA_DIR / "private" / "tickets"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
        (DATA_DIR / "private").chmod(0o700)
    except OSError:
        pass
    return d


def sanitize_filename(name: str | None) -> str:
    raw = (name or "file").strip().replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_NAME_RE.sub("_", raw).strip(" ._")
    return (cleaned or "file")[:180]


def resolve_ticket_attachment_path(rel_path: str | None) -> Path | None:
    """Resolve a stored relative path to an absolute file under DATA_DIR (no traversal)."""
    if not rel_path:
        return None
    raw = str(rel_path).replace("\\", "/").lstrip("/")
    if ".." in raw.split("/"):
        return None
    # New private store + legacy public store (pre-hardening)
    allowed_prefixes = ("private/tickets/", "uploads/tickets/")
    if not any(raw.startswith(p) for p in allowed_prefixes):
        return None
    full = (DATA_DIR / raw).resolve()
    try:
        full.relative_to(DATA_DIR.resolve())
    except ValueError:
        return None
    return full if full.is_file() else None


async def save_ticket_attachment(
    upload,
    *,
    ticket_id: int | None = None,
) -> tuple[str, str, str] | None:
    """Persist an UploadFile; return (rel_path, display_name, mime) or None if empty."""
    if upload is None:
        return None
    filename = getattr(upload, "filename", None) or ""
    if not str(filename).strip():
        return None

    display = sanitize_filename(str(filename))
    ext = Path(display).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXT:
        raise ValueError("نوع فایل مجاز نیست (تصویر، PDF، ZIP، متن یا آفیس)")

    content = await upload.read(MAX_ATTACHMENT_BYTES + 1)
    if not content:
        return None
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError("حجم فایل حداکثر ۱۲ مگابایت است")

    mime = (getattr(upload, "content_type", None) or "application/octet-stream").strip()[:128]
    stem = f"t{ticket_id or 0}_{uuid.uuid4().hex[:24]}{ext}"
    dest = _tickets_upload_dir() / stem
    dest.write_bytes(content)
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    rel = f"private/tickets/{stem}"
    return rel, display, mime


async def list_tickets(session: AsyncSession, staff: dict, *, limit: int = 100) -> list[PanelTicket]:
    """Ticket rows for the list table — no messages (keeps list payloads small)."""
    actor = actor_from_staff(staff)
    q = _scope_query(actor).limit(limit)
    return list((await session.execute(q)).scalars().all())


async def get_ticket(
    session: AsyncSession,
    staff: dict,
    ticket_id: int,
    *,
    load_messages: bool = True,
) -> Optional[PanelTicket]:
    actor = actor_from_staff(staff)
    q = select(PanelTicket).where(PanelTicket.id == int(ticket_id))
    if load_messages:
        q = q.options(selectinload(PanelTicket.messages))
    row = (await session.execute(q)).scalar_one_or_none()
    if not row:
        return None
    if actor["is_owner"]:
        return row
    if actor["role"] == "reseller" and row.opener_reseller_user_id == actor["reseller_user_id"]:
        return row
    if actor["role"] == "pg_staff" and row.opener_pg_staff_id == actor["pg_staff_id"]:
        return row
    return None


async def create_ticket(
    session: AsyncSession,
    staff: dict,
    *,
    subject: str,
    body: str,
    priority: str | None = None,
    attachment: tuple[str, str, str] | None = None,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    if not actor["is_opener"]:
        raise PermissionError("فقط نماینده / ادمین فرعی می‌تواند تیکت جدید بسازد")
    sub = (subject or "").strip()
    msg = (body or "").strip()
    if len(sub) < 3:
        raise ValueError("موضوع حداقل ۳ کاراکتر باشد")
    if len(msg) < 1 and not attachment:
        raise ValueError("متن پیام یا فایل پیوست لازم است")
    if actor["role"] == "reseller" and not actor["reseller_user_id"]:
        raise PermissionError("شناسه نماینده مشخص نیست")
    if actor["role"] == "pg_staff" and not actor["pg_staff_id"]:
        raise PermissionError("شناسه ادمین فرعی مشخص نیست")

    ticket = PanelTicket(
        subject=sub[:255],
        status=PanelTicketStatus.OPEN.value,
        priority=normalize_priority(priority),
        opener_role=actor["role"],
        opener_reseller_user_id=actor["reseller_user_id"],
        opener_pg_staff_id=actor["pg_staff_id"],
        opener_label=str(actor["label"])[:128],
        answered_unread=False,
        owner_unread=True,
    )
    session.add(ticket)
    await session.flush()
    path = name = mime = None
    if attachment:
        path, name, mime = attachment
    session.add(
        PanelTicketMessage(
            ticket_id=ticket.id,
            sender_role=actor["role"],
            sender_label=str(actor["label"])[:128],
            body=msg or (f"پیوست: {name}" if name else ""),
            attachment_path=path,
            attachment_name=name,
            attachment_mime=mime,
        )
    )
    await session.commit()
    return ticket


async def reply_ticket(
    session: AsyncSession,
    staff: dict,
    ticket_id: int,
    *,
    body: str,
    attachment: tuple[str, str, str] | None = None,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    ticket = await get_ticket(session, staff, ticket_id, load_messages=False)
    if not ticket:
        raise PermissionError("تیکت پیدا نشد")
    if ticket.status == PanelTicketStatus.CLOSED.value:
        raise ValueError("تیکت بسته است")
    msg = (body or "").strip()
    if len(msg) < 1 and not attachment:
        raise ValueError("متن پیام یا فایل پیوست لازم است")

    path = name = mime = None
    if attachment:
        path, name, mime = attachment
    session.add(
        PanelTicketMessage(
            ticket_id=ticket.id,
            sender_role=actor["role"],
            sender_label=str(actor["label"])[:128],
            body=msg or (f"پیوست: {name}" if name else ""),
            attachment_path=path,
            attachment_name=name,
            attachment_mime=mime,
        )
    )
    if actor["is_owner"]:
        ticket.status = PanelTicketStatus.ANSWERED.value
        ticket.answered_unread = True
        ticket.owner_unread = False
    else:
        ticket.status = PanelTicketStatus.OPEN.value
        ticket.answered_unread = False
        ticket.owner_unread = True
    ticket.updated_at = _utcnow()
    await session.commit()
    return ticket


async def set_status(
    session: AsyncSession,
    staff: dict,
    ticket_id: int,
    *,
    status: str,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    ticket = await get_ticket(session, staff, ticket_id, load_messages=False)
    if not ticket:
        raise PermissionError("تیکت پیدا نشد")
    new_status = normalize_status(status)
    if not new_status:
        raise ValueError("وضعیت نامعتبر است")

    if not actor["is_owner"]:
        if new_status != PanelTicketStatus.CLOSED.value:
            raise PermissionError("شما فقط می‌توانید تیکت را ببندید")

    ticket.status = new_status
    ticket.updated_at = _utcnow()
    if new_status == PanelTicketStatus.CLOSED.value:
        ticket.closed_at = _utcnow()
        ticket.answered_unread = False
        ticket.owner_unread = False
    elif new_status == PanelTicketStatus.ANSWERED.value and actor["is_owner"]:
        ticket.answered_unread = True
        ticket.owner_unread = False
    elif new_status in (PanelTicketStatus.OPEN.value, PanelTicketStatus.IN_PROGRESS.value):
        if actor["is_owner"]:
            ticket.answered_unread = False
    await session.commit()
    return ticket


async def mark_viewed(
    session: AsyncSession,
    staff: dict,
    ticket: PanelTicket,
) -> bool:
    """Clear unread flags on an already-loaded ticket. Returns True if changed."""
    actor = actor_from_staff(staff)
    changed = False
    if actor["is_owner"] and ticket.owner_unread:
        ticket.owner_unread = False
        changed = True
    elif actor["is_opener"] and ticket.answered_unread:
        ticket.answered_unread = False
        changed = True
    if changed:
        await session.commit()
    return changed


def unread_from_tickets(tickets: list[PanelTicket], staff: dict) -> int:
    """Derive unread count from an already-loaded list (same scope as sidebar)."""
    try:
        actor = actor_from_staff(staff)
    except PermissionError:
        return 0
    if actor["is_owner"]:
        return sum(1 for t in tickets if t.owner_unread)
    if actor["is_opener"]:
        return sum(1 for t in tickets if t.answered_unread)
    return 0


async def count_answered_unread(session: AsyncSession, staff: dict) -> int:
    actor = actor_from_staff(staff)
    if actor["is_owner"] or not actor["is_opener"]:
        return 0
    conds = [PanelTicket.answered_unread.is_(True)]
    if actor["role"] == "reseller" and actor["reseller_user_id"]:
        conds.append(PanelTicket.opener_reseller_user_id == int(actor["reseller_user_id"]))
    elif actor["role"] == "pg_staff" and actor["pg_staff_id"]:
        conds.append(PanelTicket.opener_pg_staff_id == int(actor["pg_staff_id"]))
    else:
        return 0
    n = (
        await session.execute(select(func.count()).select_from(PanelTicket).where(*conds))
    ).scalar_one()
    return int(n or 0)


async def count_owner_unread(session: AsyncSession, staff: dict) -> int:
    actor = actor_from_staff(staff)
    if not actor["is_owner"]:
        return 0
    n = (
        await session.execute(
            select(func.count()).select_from(PanelTicket).where(PanelTicket.owner_unread.is_(True))
        )
    ).scalar_one()
    return int(n or 0)


async def sidebar_unread_count(session: AsyncSession, staff: dict) -> int:
    """Unread count for sidebar badge / dashboard reuse."""
    try:
        actor = actor_from_staff(staff)
    except PermissionError:
        return 0
    if actor["is_owner"]:
        return await count_owner_unread(session, staff)
    if actor["is_opener"]:
        return await count_answered_unread(session, staff)
    return 0
