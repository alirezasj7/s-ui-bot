"""«متن دکمه‌ها» screens shared by the owner settings (``adm``) and the shop settings (``res``).

The section first asks whose menu (customer, admin panel, reseller panel); each audience then lists
its button groups, and a group opens the usual field list. Callback data:
``<prefix>:st:sec:labels`` audiences, ``<prefix>:st:lab:<audience>`` groups,
``<prefix>:st:sub:labels:<group>`` fields.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot import keyboards as kb
from app.services.settings_button_labels import LABEL_AUDIENCES, label_audience, label_subs_for

LABELS_SECTION = "labels"
_TITLE_PREFIXES = ("دکمه‌های ادمین — ", "دکمه‌های ")
HOME_TEXT = "🔤 <b>متن دکمه‌ها</b>\nدکمه‌های کدام منو را می‌خواهید عوض کنید؟"
AUDIENCE_TEXT = "🔤 <b>{audience}</b>\nیک گروه را انتخاب کنید."

Panel = tuple[str, InlineKeyboardMarkup]
Sub = tuple[str, str, Any]


def short_title(title: str) -> str:
    """«دکمه‌های ادمین — پلن‌ها» → «پلن‌ها»: the audience is already on screen."""
    for prefix in _TITLE_PREFIXES:
        if title.startswith(prefix):
            return title[len(prefix):]
    return title


def labels_home_panel(prefix: str, subs: list[Sub]) -> Panel:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"{prefix}:st:lab:{audience}")]
        for audience, name in LABEL_AUDIENCES
        if label_subs_for(audience, subs)
    ]
    rows.append([kb.back_button(None, f"{prefix}:st:hub")])
    return HOME_TEXT, InlineKeyboardMarkup(inline_keyboard=rows)


def labels_audience_panel(prefix: str, audience: str, subs: list[Sub]) -> Panel | None:
    groups = label_subs_for(audience, subs)
    if not groups:
        return None
    buttons = [
        InlineKeyboardButton(text=short_title(title), callback_data=f"{prefix}:st:sub:{LABELS_SECTION}:{sub_id}")
        for sub_id, title, _fields in groups
    ]
    rows = kb.pack_long_list(buttons)
    rows.append([kb.back_button(None, f"{prefix}:st:sec:{LABELS_SECTION}")])
    name = dict(LABEL_AUDIENCES).get(audience, "")
    return AUDIENCE_TEXT.format(audience=name), InlineKeyboardMarkup(inline_keyboard=rows)


def sub_back(prefix: str, sec_id: str, sub_id: str) -> str:
    """Back from a field list: a label group returns to its audience, others to their section."""
    if sec_id == LABELS_SECTION:
        return f"{prefix}:st:lab:{label_audience(sub_id)}"
    return f"{prefix}:st:sec:{sec_id}"


def resolve_sub(sections: dict[str, dict], sec_id: str, sub_id: str) -> tuple[str, Sub] | None:
    """The section and group a sub id lives in now.

    Buttons on older messages still carry where a group used to be (for example
    ``shop:btn_main``); they open its new place.
    """
    order = [sec_id, *(other for other in sections if other != sec_id)]
    for section in order:
        sub = next((s for s in (sections.get(section) or {}).get("subs") or [] if s[0] == sub_id), None)
        if sub is not None:
            return section, sub
    return None
