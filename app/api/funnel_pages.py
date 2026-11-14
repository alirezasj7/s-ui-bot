"""Customer-behaviour (funnel) page of the marketing section."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.funnel_access import funnel_shop_scope

FUNNEL_PATH = "/funnel"


def register_funnel_pages(
    app: FastAPI, *, render: Callable, require_staff: Callable, get_db: Callable,
) -> None:
    @app.get(FUNNEL_PATH)
    async def funnel_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ) -> Response:
        # Local import: home_pages imports the render helpers that this module is registered with.
        from app.api.home_pages import _EMPTY_FUNNEL, _safe_funnel
        from app.services.db_safe import recover_session

        try:
            shop_id = funnel_shop_scope(staff)
        except PermissionError:
            return RedirectResponse("/home", status_code=303)
        await recover_session(session)
        funnel = await _safe_funnel(session, reseller_id=shop_id) or dict(_EMPTY_FUNNEL)
        return render(request, "funnel.html", {"staff": staff, "funnel": funnel})
