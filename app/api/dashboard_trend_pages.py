"""JSON feed for the dashboard sales chart (7 or 30 days), scoped to the signed-in staff's shop."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dashboard_trend import ALLOWED_DAYS, sales_trend
from app.services.shop_scope import is_platform_admin, shop_owner_id

logger = logging.getLogger(__name__)


def register_dashboard_trend_pages(app, *, require_staff, get_db) -> None:
    @app.get("/home/sales-trend")
    async def home_sales_trend(
        days: int = 7,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        if days not in ALLOWED_DAYS:
            raise HTTPException(status_code=400, detail="بازهٔ نمودار معتبر نیست")
        if is_platform_admin(staff):
            shop_id = None
        else:
            shop_id = shop_owner_id(staff)
            if not shop_id:
                raise HTTPException(status_code=403, detail="دسترسی ندارید")
        try:
            trend = await sales_trend(session, reseller_id=shop_id, days=days)
        except Exception:
            logger.exception("sales trend failed shop=%s days=%s", shop_id, days)
            raise HTTPException(status_code=503, detail="دریافت نمودار ممکن نیست") from None
        return JSONResponse(trend, headers={"Cache-Control": "private, no-store"})
