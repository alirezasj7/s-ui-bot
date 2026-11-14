"""Multiple card / gateway / crypto wallet destinations (JSON in settings)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from app.services.button_styles import (
    resolve_payment_destination_style,
    serialize_item_button_style,
)

KEY_CARDS = "payment_cards"
KEY_GATEWAYS = "payment_gateways"
KEY_CRYPTO = "payment_crypto_wallets"
KEY_CARDS_RANDOM = "payment_cards_random"

MAX_ITEMS = 12

_CARD_DIGITS_RE = re.compile(r"\D")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _parse_json_list(raw: str | None) -> list[Any]:
    if not (raw or "").strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def normalize_card_number(raw: str) -> str:
    digits = _CARD_DIGITS_RE.sub("", raw or "")
    return digits[:19]


def validate_card_number(raw: str) -> str | None:
    digits = normalize_card_number(raw)
    if len(digits) < 16:
        return "شماره کارت باید حداقل ۱۶ رقم باشد"
    return None


def validate_gateway_link(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return "لینک درگاه الزامی است"
    if "{" in s:
        return None
    if not s.startswith(("http://", "https://")):
        return "لینک باید با http:// یا https:// شروع شود"
    return None


def validate_crypto_address(raw: str) -> str | None:
    if not (raw or "").strip():
        return "آدرس ولت الزامی است"
    return None


def _normalize_card(entry: dict[str, Any]) -> dict[str, Any] | None:
    number = normalize_card_number(str(entry.get("number") or entry.get("card_number") or ""))
    if not number:
        return None
    holder = str(entry.get("holder") or entry.get("card_holder") or "").strip()[:128]
    row = {
        "id": str(entry.get("id") or _new_id())[:32],
        "number": number,
        "holder": holder,
        "enabled": bool(entry.get("enabled", True)),
        "sort": int(entry.get("sort") or 0),
        **serialize_item_button_style(entry.get("button_style")),
    }
    return row


def _normalize_gateway(entry: dict[str, Any]) -> dict[str, Any] | None:
    name = str(entry.get("name") or entry.get("gateway_name") or "").strip()[:128]
    link = str(entry.get("link") or entry.get("gateway_link") or "").strip()[:2048]
    if not name and not link:
        return None
    if not name:
        name = "درگاه پرداخت"
    row = {
        "id": str(entry.get("id") or _new_id())[:32],
        "name": name,
        "link": link,
        "enabled": bool(entry.get("enabled", True)),
        "sort": int(entry.get("sort") or 0),
        **serialize_item_button_style(entry.get("button_style")),
    }
    return row


def _normalize_crypto(entry: dict[str, Any]) -> dict[str, Any] | None:
    address = str(entry.get("address") or entry.get("crypto_address") or "").strip()[:256]
    if not address:
        return None
    row = {
        "id": str(entry.get("id") or _new_id())[:32],
        "asset": str(entry.get("asset") or entry.get("crypto_asset") or "USDT").strip()[:32],
        "network": str(entry.get("network") or entry.get("crypto_network") or "TRC20").strip()[:32],
        "address": address,
        "enabled": bool(entry.get("enabled", True)),
        "sort": int(entry.get("sort") or 0),
        **serialize_item_button_style(entry.get("button_style")),
    }
    return row


def _dedupe_sort(items: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, item in enumerate(sorted(items, key=lambda x: (x.get("sort", 0), x.get("id", "")))):
        k = key_fn(item)
        if not k or k in seen:
            continue
        seen.add(k)
        row = dict(item)
        row["sort"] = i
        out.append(row)
        if len(out) >= MAX_ITEMS:
            break
    return out


def parse_payment_cards(raw: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _parse_json_list(raw):
        if not isinstance(entry, dict):
            continue
        row = _normalize_card(entry)
        if row:
            out.append(row)
    return _dedupe_sort(out, lambda x: x["number"])


def parse_payment_gateways(raw: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _parse_json_list(raw):
        if not isinstance(entry, dict):
            continue
        row = _normalize_gateway(entry)
        if row:
            out.append(row)
    return _dedupe_sort(out, lambda x: (x.get("link") or x.get("name") or "").lower())


def parse_payment_crypto_wallets(raw: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _parse_json_list(raw):
        if not isinstance(entry, dict):
            continue
        row = _normalize_crypto(entry)
        if row:
            out.append(row)
    return _dedupe_sort(out, lambda x: x["address"].lower())


def dump_payment_cards(items: list[dict[str, Any]]) -> str:
    return json.dumps(parse_payment_cards(json.dumps(items)), ensure_ascii=False)


def dump_payment_gateways(items: list[dict[str, Any]]) -> str:
    return json.dumps(parse_payment_gateways(json.dumps(items)), ensure_ascii=False)


def dump_payment_crypto_wallets(items: list[dict[str, Any]]) -> str:
    return json.dumps(parse_payment_crypto_wallets(json.dumps(items)), ensure_ascii=False)


def migrate_legacy_payment_settings(data: dict[str, str]) -> dict[str, str]:
    """Ensure JSON lists exist and legacy single-value keys stay in sync."""
    out = dict(data)

    cards = parse_payment_cards(out.get(KEY_CARDS))
    if not cards:
        legacy_num = normalize_card_number(out.get("card_number") or "")
        legacy_holder = (out.get("card_holder") or "").strip()
        if legacy_num:
            cards = [
                {
                    "id": _new_id(),
                    "number": legacy_num,
                    "holder": legacy_holder,
                    "enabled": True,
                    "sort": 0,
                }
            ]
            out[KEY_CARDS] = dump_payment_cards(cards)

    gateways = parse_payment_gateways(out.get(KEY_GATEWAYS))
    if not gateways:
        link = (out.get("gateway_link") or "").strip()
        name = (out.get("gateway_name") or "").strip()
        if link or name:
            gateways = [
                {
                    "id": _new_id(),
                    "name": name or "درگاه پرداخت",
                    "link": link,
                    "enabled": True,
                    "sort": 0,
                }
            ]
            out[KEY_GATEWAYS] = dump_payment_gateways(gateways)

    crypto = parse_payment_crypto_wallets(out.get(KEY_CRYPTO))
    if not crypto:
        address = (out.get("crypto_address") or "").strip()
        if address:
            crypto = [
                {
                    "id": _new_id(),
                    "asset": (out.get("crypto_asset") or "USDT").strip(),
                    "network": (out.get("crypto_network") or "TRC20").strip(),
                    "address": address,
                    "enabled": True,
                    "sort": 0,
                }
            ]
            out[KEY_CRYPTO] = dump_payment_crypto_wallets(crypto)

    if cards:
        out["card_number"] = cards[0]["number"]
        out["card_holder"] = cards[0].get("holder") or ""
    if gateways:
        out["gateway_name"] = gateways[0].get("name") or ""
        out["gateway_link"] = gateways[0].get("link") or ""
    if crypto:
        out["crypto_asset"] = crypto[0].get("asset") or "USDT"
        out["crypto_network"] = crypto[0].get("network") or "TRC20"
        out["crypto_address"] = crypto[0].get("address") or ""

    return out


def enrich_payment_settings(data: dict[str, str]) -> dict[str, str]:
    return migrate_legacy_payment_settings(data)


def enabled_cards(ui: dict[str, str]) -> list[dict[str, Any]]:
    ui = enrich_payment_settings(ui)
    return [c for c in parse_payment_cards(ui.get(KEY_CARDS)) if c.get("enabled", True)]


def enabled_gateways(ui: dict[str, str]) -> list[dict[str, Any]]:
    ui = enrich_payment_settings(ui)
    return [g for g in parse_payment_gateways(ui.get(KEY_GATEWAYS)) if g.get("enabled", True)]


def enabled_crypto_wallets(ui: dict[str, str]) -> list[dict[str, Any]]:
    ui = enrich_payment_settings(ui)
    return [w for w in parse_payment_crypto_wallets(ui.get(KEY_CRYPTO)) if w.get("enabled", True)]


def random_card_enabled(ui: dict[str, str]) -> bool:
    """«نمایش کارت تصادفی»: with several cards the customer is shown one instead of choosing."""
    return str(ui.get(KEY_CARDS_RANDOM, "0")).strip().lower() in {"1", "true", "yes", "on"}


def pick_card(cards: list[dict[str, Any]], seed: str) -> dict[str, Any]:
    """One of ``cards``, spread evenly over different ``seed`` values and stable for the same seed.

    The seed is the order (or top-up) the card is shown for, so a customer who taps «کارت به کارت»
    again for the same order sees the same card instead of a different one.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return cards[int.from_bytes(digest[:8], "big") % len(cards)]


def card_by_id(ui: dict[str, str], dest_id: str) -> dict[str, Any] | None:
    for row in enabled_cards(ui):
        if str(row.get("id")) == str(dest_id):
            return row
    return None


def gateway_by_id(ui: dict[str, str], dest_id: str) -> dict[str, Any] | None:
    for row in enabled_gateways(ui):
        if str(row.get("id")) == str(dest_id):
            return row
    return None


def crypto_by_id(ui: dict[str, str], dest_id: str) -> dict[str, Any] | None:
    for row in enabled_crypto_wallets(ui):
        if str(row.get("id")) == str(dest_id):
            return row
    return None


async def get_payment_cards(session, *, reseller_id: int | None = None) -> list[dict[str, Any]]:
    from app.services.users import get_setting

    raw = await get_setting(session, KEY_CARDS, reseller_id=reseller_id)
    ui = enrich_payment_settings({KEY_CARDS: raw or "[]"})
    return parse_payment_cards(ui.get(KEY_CARDS))


async def save_payment_cards(
    session,
    items: list[dict[str, Any]],
    *,
    reseller_id: int | None = None,
) -> list[dict[str, Any]]:
    from app.services.users import set_setting

    cleaned = parse_payment_cards(json.dumps(items))
    payload = dump_payment_cards(cleaned)
    await set_setting(session, KEY_CARDS, payload, reseller_id=reseller_id)
    if cleaned:
        await set_setting(session, "card_number", cleaned[0]["number"], reseller_id=reseller_id)
        await set_setting(session, "card_holder", cleaned[0].get("holder") or "", reseller_id=reseller_id)
    else:
        await set_setting(session, "card_number", "", reseller_id=reseller_id)
        await set_setting(session, "card_holder", "", reseller_id=reseller_id)
    return cleaned


async def get_payment_gateways(session, *, reseller_id: int | None = None) -> list[dict[str, Any]]:
    from app.services.users import get_setting

    raw = await get_setting(session, KEY_GATEWAYS, reseller_id=reseller_id)
    ui = enrich_payment_settings({KEY_GATEWAYS: raw or "[]"})
    return parse_payment_gateways(ui.get(KEY_GATEWAYS))


async def save_payment_gateways(
    session,
    items: list[dict[str, Any]],
    *,
    reseller_id: int | None = None,
) -> list[dict[str, Any]]:
    from app.services.users import set_setting

    cleaned = parse_payment_gateways(json.dumps(items))
    payload = dump_payment_gateways(cleaned)
    await set_setting(session, KEY_GATEWAYS, payload, reseller_id=reseller_id)
    if cleaned:
        await set_setting(session, "gateway_name", cleaned[0].get("name") or "", reseller_id=reseller_id)
        await set_setting(session, "gateway_link", cleaned[0].get("link") or "", reseller_id=reseller_id)
    else:
        await set_setting(session, "gateway_name", "", reseller_id=reseller_id)
        await set_setting(session, "gateway_link", "", reseller_id=reseller_id)
    return cleaned


async def get_payment_crypto_wallets(
    session, *, reseller_id: int | None = None
) -> list[dict[str, Any]]:
    from app.services.users import get_setting

    raw = await get_setting(session, KEY_CRYPTO, reseller_id=reseller_id)
    ui = enrich_payment_settings({KEY_CRYPTO: raw or "[]"})
    return parse_payment_crypto_wallets(ui.get(KEY_CRYPTO))


async def save_payment_crypto_wallets(
    session,
    items: list[dict[str, Any]],
    *,
    reseller_id: int | None = None,
) -> list[dict[str, Any]]:
    from app.services.users import set_setting

    cleaned = parse_payment_crypto_wallets(json.dumps(items))
    payload = dump_payment_crypto_wallets(cleaned)
    await set_setting(session, KEY_CRYPTO, payload, reseller_id=reseller_id)
    if cleaned:
        await set_setting(session, "crypto_asset", cleaned[0].get("asset") or "USDT", reseller_id=reseller_id)
        await set_setting(session, "crypto_network", cleaned[0].get("network") or "TRC20", reseller_id=reseller_id)
        await set_setting(session, "crypto_address", cleaned[0].get("address") or "", reseller_id=reseller_id)
    else:
        await set_setting(session, "crypto_asset", "USDT", reseller_id=reseller_id)
        await set_setting(session, "crypto_network", "TRC20", reseller_id=reseller_id)
        await set_setting(session, "crypto_address", "", reseller_id=reseller_id)
    return cleaned


def inline_picker_markup(
    method: str,
    items: list[dict[str, Any]],
    *,
    order_id: int,
    prefix: str,
    ui: dict | None = None,
) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[InlineKeyboardButton]] = []
    for group in destination_picker_rows(method, items, order_id=order_id, prefix=prefix):
        row_btns: list[InlineKeyboardButton] = []
        for label, cb in group:
            item_id = cb.rsplit(":", 1)[-1]
            item = next((x for x in items if str(x.get("id")) == item_id), None)
            style = resolve_payment_destination_style(ui, item, method)
            kwargs: dict[str, Any] = {"text": label, "callback_data": cb}
            if style:
                kwargs["style"] = style
            row_btns.append(InlineKeyboardButton(**kwargs))
        rows.append(row_btns)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def destination_picker_rows(
    method: str,
    items: list[dict[str, Any]],
    *,
    order_id: int,
    prefix: str,
) -> list[list[tuple[str, str]]]:
    """Build inline-keyboard rows [(label, callback_data), ...]."""
    rows: list[list[tuple[str, str]]] = []
    for item in items[:8]:
        if method == "card":
            label = f"💳 …{item['number'][-4:]}"
            if item.get("holder"):
                label = f"{label} ({item['holder'][:12]})"
            cb = f"{prefix}:card:{order_id}:{item['id']}"
        elif method == "gateway":
            label = f"🌐 {(item.get('name') or 'درگاه')[:24]}"
            cb = f"{prefix}:gateway:{order_id}:{item['id']}"
        else:
            asset = item.get("asset") or "USDT"
            label = f"💎 {asset} …{item['address'][-6:]}"
            cb = f"{prefix}:crypto:{order_id}:{item['id']}"
        rows.append([(label, cb)])
    return rows
