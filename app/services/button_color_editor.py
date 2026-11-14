"""Rules for changing button colors from the bot settings screens.

The platform owner may color every catalog button. A shop owner may color the
buttons ``allowed_style_setting_keys(for_reseller=True)`` allows, and only in
their own shop's settings. Every write re-checks both rules, so a forged
callback cannot reach an admin-only color or another shop.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.button_styles import (
    CATALOG_BY_ID,
    STYLE_OPTIONS,
    allowed_style_setting_keys,
    get_button_style,
    grouped_catalog,
    normalize_style,
    setting_key,
    style_ids_sharing_setting,
)
from app.services.users import set_setting

COLOR_CHOICES: tuple[str, ...] = tuple(value for value, _label, _tone in STYLE_OPTIONS)
COLOR_NAMES: dict[str, str] = {value: label for value, label, _tone in STYLE_OPTIONS}
COLOR_SWATCHES: dict[str, str] = {"": "⚪", "primary": "🔵", "success": "🟢", "danger": "🔴"}
# set_setting treats None as "the current shop context"; 0 always means platform
# settings, so a shop context left on the task can never redirect an owner write.
PLATFORM_SCOPE = 0


@dataclass(frozen=True, slots=True)
class ColorItem:
    style_id: str
    label: str
    color: str
    default: str

    @property
    def is_default(self) -> bool:
        return self.color == self.default


@dataclass(frozen=True, slots=True)
class ColorGroup:
    name: str
    items: tuple[ColorItem, ...]


def color_groups(ui: dict[str, str], *, for_reseller: bool) -> list[ColorGroup]:
    """Catalog groups the actor may edit, with each button's current color."""
    groups: list[ColorGroup] = []
    for name, rows in grouped_catalog(for_reseller=for_reseller):
        items = tuple(
            ColorItem(
                style_id=row["id"],
                label=row["label"],
                color=get_button_style(ui, row["id"]),
                default=normalize_style(row["default"]),
            )
            for row in rows
        )
        groups.append(ColorGroup(name=name, items=items))
    return groups


def find_color_item(ui: dict[str, str], style_id: str, *, for_reseller: bool) -> ColorItem:
    """The editable item for *style_id*, or ValueError when the actor may not edit it."""
    _require_editable(style_id, for_reseller=for_reseller)
    for group in color_groups(ui, for_reseller=for_reseller):
        for item in group.items:
            if item.style_id == style_id:
                return item
    raise ValueError("این دکمه قابل تغییر رنگ نیست")


def shared_button_count(style_id: str) -> int:
    """How many reply/inline button ids read their color from this setting."""
    return len(style_ids_sharing_setting(style_id))


async def set_button_color(
    session: AsyncSession,
    *,
    style_id: str,
    color: str,
    for_reseller: bool,
    shop_id: int | None,
) -> str:
    """Store *color* for *style_id* in the actor's own settings and return it."""
    if color not in COLOR_CHOICES:
        raise ValueError("رنگ نامعتبر است")
    _require_editable(style_id, for_reseller=for_reseller)
    if for_reseller and not shop_id:
        raise ValueError("فروشگاه مشخص نیست")
    await set_setting(
        session,
        setting_key(style_id),
        color,
        reseller_id=shop_id if for_reseller else PLATFORM_SCOPE,
    )
    return color


async def reset_button_color(
    session: AsyncSession,
    *,
    style_id: str,
    for_reseller: bool,
    shop_id: int | None,
) -> str:
    """Restore the catalog default color for *style_id* and return it."""
    _require_editable(style_id, for_reseller=for_reseller)
    default = normalize_style(CATALOG_BY_ID[style_id]["default"])
    return await set_button_color(
        session, style_id=style_id, color=default, for_reseller=for_reseller, shop_id=shop_id
    )


def _require_editable(style_id: str, *, for_reseller: bool) -> None:
    # Aliases share a canonical row; only canonical catalog ids are listed and saved.
    if style_id not in CATALOG_BY_ID:
        raise ValueError("این دکمه قابل تغییر رنگ نیست")
    if setting_key(style_id) not in allowed_style_setting_keys(for_reseller=for_reseller):
        raise ValueError("این دکمه قابل تغییر رنگ نیست")
