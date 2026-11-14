"""Owner monitoring account, public label and ordering text prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.connection_status_admin_ui import monitor_error, reopen_monitor_home
from app.bot.connection_status_ui import admin_page_keyboard, admin_page_text, bot_monitor_access, target_keyboard, target_text
from app.bot.nav_input import CancelEntry, delete_user_message, finish_text_step, register_cancel_code, try_legacy_cancel
from app.bot.tg_utils import parse_bot_int
from app.db.models import BotUser
from app.services.connection_monitor_actions import edit_monitor_target
from app.services.connection_monitor_settings import set_monitor_account
from app.services.connection_monitor_views import monitor_admin_page, monitor_target_view
from app.services.users import get_all_settings


router = Router(name="connection_status_admin_input")
CANCEL_CODE = "monitor_admin"


class MonitorInput(StatesGroup):
    account = State()
    public_name = State()
    display_order = State()


register_cancel_code(CANCEL_CODE, CancelEntry(reopen=reopen_monitor_home))


@router.message(MonitorInput.account, F.text)
@router.message(MonitorInput.public_name, F.text)
@router.message(MonitorInput.display_order, F.text)
async def monitor_input(message: Message, session: AsyncSession, db_user: BotUser, state: FSMContext,
                         is_reseller_bot: bool = False) -> None:
    if kb.is_cancel_text(message.text):
        await try_legacy_cancel(message, state, session, db_user, is_reseller_bot=is_reseller_bot)
        return
    try:
        access = await bot_monitor_access(session, db_user, is_reseller_bot=is_reseller_bot)
        current = await state.get_state()
        if current == MonitorInput.account.state:
            await delete_user_message(message)
            await set_monitor_account(session, access, username=(message.text or "").strip())
            await state.set_state(None)
            page = await monitor_admin_page(session, access, now=datetime.now(timezone.utc))
            ui = await get_all_settings(session)
            await session.commit()
            await finish_text_step(message, state, text=admin_page_text(page, ui), inline=admin_page_keyboard(page, ui))
            return
        data = await state.get_data()
        target_id = data.get("monitor_target_id")
        field = "public_name" if current == MonitorInput.public_name.state else "display_order"
        value = message.text if field == "public_name" else parse_bot_int(message.text)
        await edit_monitor_target(session, access, target_id=target_id, field=field, value=value)
        await state.set_state(None)
        target = await monitor_target_view(session, access, target_id=target_id, now=datetime.now(timezone.utc))
        ui = await get_all_settings(session)
        await session.commit()
        await finish_text_step(message, state, text=target_text(target), inline=target_keyboard(target, ui))
    except Exception as exc:
        await monitor_error(message, session, exc)
