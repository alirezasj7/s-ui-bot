"""Quote shop prices without changing stored catalog prices or existing orders."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CatalogDiscount, Plan, ServiceAddonPack
from app.services.formatting import format_toman
from app.services.gift_codes import expiry_input, utc

MAX_PRICE = 2_000_000_000
MAX_ACTIVE_DISCOUNTS = 100
ProductKind = Literal["fixed", "custom", "addon"]


@dataclass(frozen=True, slots=True)
class PriceTarget:
    amount: int
    kind: ProductKind = "fixed"
    plan_id: int | None = None
    category_id: int | None = None
    is_trial: bool = False


@dataclass(frozen=True, slots=True)
class PriceQuote:
    price: int
    original_price: int | None = None
    ends_at: datetime | None = None

    def payload(self) -> dict[str, int | str | None]:
        return {
            "price": self.price,
            "original_price": self.original_price,
            "discount_ends_at": self.ends_at.isoformat() if self.ends_at else None,
        }


async def active_discounts(session: AsyncSession, *, shop_id: int | None) -> list[CatalogDiscount]:
    now = datetime.now(timezone.utc)
    return list((await session.scalars(select(CatalogDiscount).where(
        CatalogDiscount.shop_key == (shop_id or 0),
        CatalogDiscount.reseller_id == shop_id,
        CatalogDiscount.is_active.is_(True),
        or_(CatalogDiscount.ends_at.is_(None), CatalogDiscount.ends_at > now),
    ).order_by(CatalogDiscount.id).limit(MAX_ACTIVE_DISCOUNTS))).all())


def matches(rule: CatalogDiscount, target: PriceTarget) -> bool:
    return {
        "all": True,
        "fixed": target.kind == "fixed",
        "plan": target.kind == "fixed" and rule.plan_id is not None and rule.plan_id == target.plan_id,
        "category": target.category_id is not None and rule.category_id == target.category_id,
    }.get(rule.scope, False)


def reduced_price(amount: int, rule: CatalogDiscount) -> int:
    reduction = amount * rule.reduction_value // 100 if rule.reduction_kind == "percent" else rule.reduction_value
    return max(0, amount - reduction)


def quote_price(target: PriceTarget, rules: list[CatalogDiscount], *, now: datetime | None = None) -> PriceQuote:
    if type(target.amount) is not int or not 0 <= target.amount <= MAX_PRICE:
        raise ValueError("قیمت نامعتبر است")
    if target.is_trial:
        return PriceQuote(target.amount)
    now = utc(now or datetime.now(timezone.utc))
    applicable = [r for r in rules if r.is_active and matches(r, target) and (r.ends_at is None or utc(r.ends_at) > now)]
    # Overlapping adjustments never stack within a mode; choose the customer's best price.
    base = min([target.amount] + [reduced_price(target.amount, r) for r in applicable if r.mode == "permanent"])
    offers = [(reduced_price(base, r), r.id or 0, r) for r in applicable if r.mode == "temporary"]
    if not offers:
        return PriceQuote(base)
    price, _, rule = min(offers, key=lambda item: item[:2])
    return PriceQuote(price, base if price < base else None, utc(rule.ends_at) if price < base and rule.ends_at else None)


def product_target(product: Plan | ServiceAddonPack) -> PriceTarget:
    return PriceTarget(
        amount=product.price,
        kind="addon" if isinstance(product, ServiceAddonPack) else "fixed",
        plan_id=product.id if isinstance(product, Plan) else None,
        category_id=product.category_id,
        is_trial=bool(getattr(product, "is_trial", False)),
    )


async def quote_product(session: AsyncSession, product: Plan | ServiceAddonPack, *, shop_id: int | None) -> PriceQuote:
    if product.owner_reseller_id != shop_id:
        raise ValueError("محصول این فروشگاه نیست")
    quote = quote_price(product_target(product), await active_discounts(session, shop_id=shop_id))
    product.__dict__["catalog_quote"] = quote
    return quote


async def annotate_prices(session: AsyncSession, products: list[Plan | ServiceAddonPack], *, shop_id: int | None) -> None:
    rules = await active_discounts(session, shop_id=shop_id)
    for product in products:
        if product.owner_reseller_id != shop_id:
            raise ValueError("محصول این فروشگاه نیست")
        product.__dict__["catalog_quote"] = quote_price(product_target(product), rules)


def displayed_quote(product: Plan | ServiceAddonPack) -> PriceQuote:
    return product.__dict__.get("catalog_quote", PriceQuote(product.price))


def sale_price(product: Plan | ServiceAddonPack) -> int:
    return displayed_quote(product).price


def price_html(quote: PriceQuote, currency: str = "تومان") -> str:
    current = html.escape(format_toman(quote.price, currency))
    if quote.original_price is None:
        return f"<b>{current}</b>"
    previous = html.escape(format_toman(quote.original_price, currency))
    deadline = html.escape(expiry_input(quote.ends_at) + " (تهران)") if quote.ends_at else ""
    return f"<s>{previous}</s> ← <b>{current}</b>\nتخفیف تا {deadline}"


def assert_expected_price(quote: PriceQuote, expected_price: int | None) -> None:
    if expected_price is None:
        return
    if type(expected_price) is not int or not 0 <= expected_price <= MAX_PRICE:
        raise ValueError("قیمت تأییدشده نامعتبر است")
    if quote.price != expected_price:
        raise ValueError("قیمت تغییر کرده است؛ صفحه را تازه کنید و دوباره تأیید کنید")
