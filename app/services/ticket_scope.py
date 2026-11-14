"""Which shop a support ticket belongs to (the shop stamped on it when it was created)."""

from __future__ import annotations

from app.db.models import Ticket
from app.services.shop_scope import is_platform_admin, shop_owner_id


def ticket_shop_clause(shop_id: int | None):
    """SQL scope of a ticket list: the shop stamped on the ticket, NULL meaning the platform."""
    if shop_id:
        return Ticket.reseller_id == int(shop_id)
    return Ticket.reseller_id.is_(None)


def staff_ticket_in_scope(staff: dict, ticket: Ticket) -> bool:
    """Staff may handle a customer ticket only of their own shop (platform Owner: platform tickets)."""
    if is_platform_admin(staff):
        return ticket.reseller_id is None
    rid = shop_owner_id(staff)
    return bool(rid) and ticket.reseller_id is not None and int(ticket.reseller_id) == int(rid)
