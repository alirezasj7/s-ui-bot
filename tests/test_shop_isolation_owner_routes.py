"""The platform Owner cannot reach another shop's customers, wallet or audience."""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, Payment, PaymentStatus
from app.services.broadcast import list_broadcast_targets, send_broadcast
from app.services.shop_scope import platform_may_review_payment
from tests.test_update_owner_only import OWNER_SESSION, RoutesHarness

SHOP_ID = 5


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[int] = []

    async def send_message(self, chat_id: int, *_args, **_kwargs) -> None:
        self.sent.append(chat_id)


class OwnerShopBoundaryTests(RoutesHarness):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            session.add_all([
                BotUser(id=7, telegram_id=107, referral_code="shopcust", role="user", reseller_id=SHOP_ID),
                BotUser(id=8, telegram_id=108, referral_code="platcust", role="user"),
            ])
            await session.commit()

    async def post(self, path: str, **form: str):
        cookie = f"session={self.signer.dumps(OWNER_SESSION)}; csrf=token"
        headers = {"cookie": cookie, "x-csrf-token": "token", "origin": "http://panel.test"}
        return await self.client.post(path, headers=headers, data=form)

    async def exists(self, model, pk: int) -> bool:
        async with AsyncSession(bind=self.engine) as session:
            return await session.get(model, pk) is not None

    async def test_owner_cannot_delete_a_shop_customer_from_the_resellers_tab(self):
        response = await self.post("/resellers/7/delete-user", reason="cleanup request")
        self.assertEqual(response.status_code, 303)
        self.assertIn("err", parse_qs(urlsplit(response.headers["location"]).query))
        self.assertTrue(await self.exists(BotUser, 7))

    async def test_owner_can_still_delete_a_platform_user_from_the_resellers_tab(self):
        response = await self.post("/resellers/8/delete-user", reason="cleanup request")
        self.assertEqual(response.status_code, 303)
        self.assertIn("ok", parse_qs(urlsplit(response.headers["location"]).query))
        self.assertFalse(await self.exists(BotUser, 8))

    async def test_owner_cannot_approve_a_shop_wallet_topup(self):
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            session.add(Payment(
                id=31, user_id=7, amount=50_000, is_wallet_topup=True, wallet_shop_id=SHOP_ID,
                status=PaymentStatus.PENDING.value,
            ))
            await session.commit()
        response = await self.post("/payments/31/approve")
        self.assertIn("err", parse_qs(urlsplit(response.headers["location"]).query))
        async with AsyncSession(bind=self.engine) as session:
            payment = await session.get(Payment, 31)
            customer = await session.get(BotUser, 7)
        self.assertEqual(payment.status, PaymentStatus.PENDING.value)
        self.assertEqual(customer.wallet_balance, 0)

    async def test_owner_cannot_reject_a_shop_wallet_topup(self):
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            session.add(Payment(
                id=32, user_id=7, amount=50_000, is_wallet_topup=True, wallet_shop_id=SHOP_ID,
                status=PaymentStatus.PENDING.value,
            ))
            await session.commit()
        response = await self.post("/payments/32/reject")
        self.assertIn("err", parse_qs(urlsplit(response.headers["location"]).query))
        async with AsyncSession(bind=self.engine) as session:
            self.assertEqual((await session.get(Payment, 32)).status, PaymentStatus.PENDING.value)

    async def test_broadcast_audience_excludes_shop_customers(self):
        for audience in ("all", "users", "resellers", "admins"):
            async with AsyncSession(bind=self.engine) as session:
                targets = await list_broadcast_targets(session, audience=audience)
                target_ids = {int(u.id) for u in targets}
            self.assertNotIn(7, target_ids, audience)
        async with AsyncSession(bind=self.engine, expire_on_commit=False) as session:
            bot = FakeBot()
            result = await send_broadcast(bot, session, text="hello", audience="all", delay=0)
        self.assertNotIn(107, bot.sent)
        self.assertIn(108, bot.sent)
        self.assertEqual(result["total"], len(bot.sent))


class PlatformPaymentReviewRuleTests(RoutesHarness):
    def test_rule_matches_the_bot_for_every_payment_kind(self):
        shop_order = Order(id=1, user_id=7, reseller_id=SHOP_ID, amount=1)
        platform_order = Order(id=2, user_id=8, reseller_id=None, amount=1)
        platform_topup = Payment(user_id=8, amount=1, is_wallet_topup=True, wallet_shop_id=None)
        shop_topup = Payment(user_id=7, amount=1, is_wallet_topup=True, wallet_shop_id=SHOP_ID)
        order_payment = Payment(user_id=8, amount=1, is_wallet_topup=False)
        self.assertTrue(platform_may_review_payment(platform_topup, None))
        self.assertFalse(platform_may_review_payment(shop_topup, None))
        self.assertTrue(platform_may_review_payment(order_payment, platform_order))
        self.assertFalse(platform_may_review_payment(order_payment, shop_order))
        self.assertTrue(platform_may_review_payment(order_payment, None))
