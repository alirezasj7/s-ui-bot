"""Who may open the customer-behaviour (funnel) page, and for which shop."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.authz import authz_from_staff, can_shop
from app.services.shop_scope import is_platform_admin, shop_owner_id


def funnel_shop_scope(staff: Mapping[str, Any]) -> int | None:
    """Shop whose funnel ``staff`` may read (``None`` = the platform shop).

    Same rule as the finance report tabs the panel came from: the orders or payments
    permission, an explicit Owner for the platform shop, and a shop of their own for
    everyone else. Raises ``PermissionError`` otherwise.
    """
    authz = authz_from_staff(staff)
    if not (can_shop(authz, "orders") or can_shop(authz, "payments")):
        raise PermissionError("دسترسی به رفتار کاربر ندارید")
    if is_platform_admin(dict(staff)):
        return None
    shop_id = shop_owner_id(dict(staff))
    if not shop_id:
        raise PermissionError("محدوده فروشگاه مشخص نیست")
    return shop_id
