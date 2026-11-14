"""Phase 0 — payment review diagnosis (shared bot + web)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class PaymentReviewDiagTests(unittest.IsolatedAsyncioTestCase):
    async def _session(self):
        from app.db.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        return engine, Session

    async def test_pending_is_claimable(self):
        from app.db.models import BotUser, Payment, PaymentMethod, PaymentStatus, Role
        from app.services.payment_review_diag import diagnose_payment_review

        engine, Session = await self._session()
        async with Session() as session:
            user = BotUser(telegram_id=8001, referral_code="D8001", role=Role.USER.value)
            session.add(user)
            await session.flush()
            pay = Payment(
                user_id=user.id,
                amount=1000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.PENDING.value,
                is_wallet_topup=True,
            )
            session.add(pay)
            await session.commit()
            await session.refresh(pay)
            diag = await diagnose_payment_review(session, pay)
            self.assertEqual(diag.kind, "pending")
            self.assertTrue(diag.can_claim_approve)
            self.assertFalse(diag.can_resume_fulfill)
        await engine.dispose()

    async def test_approved_paid_incomplete_is_fulfill(self):
        from app.db.models import (
            BotUser,
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentStatus,
            Plan,
            Role,
        )
        from app.services.payment_review_diag import diagnose_payment_review

        engine, Session = await self._session()
        async with Session() as session:
            user = BotUser(telegram_id=8002, referral_code="D8002", role=Role.USER.value)
            plan = Plan(name="P", price=10000, data_limit_gb=10, duration_days=30)
            session.add_all([user, plan])
            await session.flush()
            order = Order(
                user_id=user.id,
                plan_id=plan.id,
                amount=10000,
                status=OrderStatus.PAID.value,
                payment_method=PaymentMethod.CARD.value,
            )
            session.add(order)
            await session.flush()
            pay = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=10000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.APPROVED.value,
                reviewed_by=1,
            )
            session.add(pay)
            await session.commit()
            await session.refresh(pay)
            await session.refresh(order)
            diag = await diagnose_payment_review(session, pay, order=order)
            self.assertEqual(diag.kind, "approved_fulfill")
            self.assertTrue(diag.can_resume_fulfill)
            self.assertFalse(diag.can_resend_telegram)
            self.assertIn("تحویل", diag.label_fa)
        await engine.dispose()

    async def test_delivered_with_open_failure_is_resend(self):
        from app.db.models import (
            BotUser,
            DeliveryFailure,
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentStatus,
            Plan,
            Role,
            UserService,
        )
        from app.services.payment_review_diag import diagnose_payment_review

        engine, Session = await self._session()
        async with Session() as session:
            user = BotUser(telegram_id=8003, referral_code="D8003", role=Role.USER.value)
            plan = Plan(name="P3", price=5000, data_limit_gb=5, duration_days=30)
            session.add_all([user, plan])
            await session.flush()
            svc = UserService(
                bot_user_id=user.id,
                plan_id=plan.id,
                pg_username="u8003",
                remark="order:x",
            )
            session.add(svc)
            await session.flush()
            order = Order(
                user_id=user.id,
                plan_id=plan.id,
                amount=5000,
                status=OrderStatus.DELIVERED.value,
                payment_method=PaymentMethod.CARD.value,
                service_id=svc.id,
            )
            session.add(order)
            await session.flush()
            pay = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=5000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.APPROVED.value,
                reviewed_by=1,
                review_note="delivery_failed",
            )
            session.add(pay)
            await session.flush()
            session.add(
                DeliveryFailure(
                    order_id=order.id,
                    payment_id=pay.id,
                    error="telegram send failed",
                    attempts=2,
                )
            )
            await session.commit()
            await session.refresh(pay)
            await session.refresh(order)
            diag = await diagnose_payment_review(session, pay, order=order)
            self.assertEqual(diag.kind, "approved_resend")
            self.assertTrue(diag.can_resend_telegram)
            self.assertFalse(diag.can_resume_fulfill)
            self.assertFalse(diag.can_claim_approve)
            self.assertIn("تلگرام", diag.label_fa)
        await engine.dispose()

    async def test_fully_complete_without_failure(self):
        from app.db.models import (
            BotUser,
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentStatus,
            Plan,
            Role,
            UserService,
        )
        from app.services.payment_review_diag import diagnose_payment_review

        engine, Session = await self._session()
        async with Session() as session:
            user = BotUser(telegram_id=8004, referral_code="D8004", role=Role.USER.value)
            plan = Plan(name="P4", price=5000, data_limit_gb=5, duration_days=30)
            session.add_all([user, plan])
            await session.flush()
            svc = UserService(
                bot_user_id=user.id,
                plan_id=plan.id,
                pg_username="u8004",
                remark="order:y",
            )
            session.add(svc)
            await session.flush()
            order = Order(
                user_id=user.id,
                plan_id=plan.id,
                amount=5000,
                status=OrderStatus.DELIVERED.value,
                payment_method=PaymentMethod.CARD.value,
                service_id=svc.id,
            )
            session.add(order)
            await session.flush()
            pay = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=5000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.APPROVED.value,
                reviewed_by=1,
            )
            session.add(pay)
            await session.commit()
            await session.refresh(pay)
            diag = await diagnose_payment_review(session, pay, order=order)
            self.assertEqual(diag.kind, "approved_complete")
            self.assertIn("تحویل شده", diag.alert_fa)
        await engine.dispose()

    async def test_wallet_resume_vs_done(self):
        from app.db.models import (
            BotUser,
            Payment,
            PaymentMethod,
            PaymentStatus,
            Role,
            WalletTransaction,
        )
        from app.services.orders import _wallet_topup_credit_reason
        from app.services.payment_review_diag import diagnose_payment_review

        engine, Session = await self._session()
        async with Session() as session:
            user = BotUser(
                telegram_id=8005,
                referral_code="D8005",
                role=Role.USER.value,
                wallet_balance=0,
            )
            session.add(user)
            await session.flush()
            pay = Payment(
                user_id=user.id,
                amount=12000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.APPROVED.value,
                is_wallet_topup=True,
                reviewed_by=1,
            )
            session.add(pay)
            await session.commit()
            await session.refresh(pay)

            diag = await diagnose_payment_review(session, pay)
            self.assertEqual(diag.kind, "approved_wallet_resume")
            self.assertTrue(diag.can_resume_fulfill)

            session.add(
                WalletTransaction(
                    user_id=user.id,
                    amount=12000,
                    reason=_wallet_topup_credit_reason(int(pay.id)),
                    balance_after=12000,
                )
            )
            await session.commit()
            diag2 = await diagnose_payment_review(session, pay)
            self.assertEqual(diag2.kind, "approved_wallet_done")
            self.assertFalse(diag2.can_resume_fulfill)
        await engine.dispose()


class PayrevHandlerWiringTests(unittest.TestCase):
    def test_handler_uses_diagnosis_and_resend_path(self):
        src = Path("app/bot/handlers/payments.py").read_text(encoding="utf-8")
        # Phase 1: dedicated go/send + legacy ok router
        self.assertIn("execute_payment_legacy_ok", src)
        self.assertIn("execute_payment_resend", src)
        self.assertIn("payrev:send:", src)
        actions = Path("app/services/payment_review_actions.py").read_text(encoding="utf-8")
        self.assertIn("پیام تحویل دوباره ارسال شد", actions)
        self.assertIn("diagnose_payment_review", actions)

    def test_finance_delivery_surfaces_diag(self):
        pages = Path("app/api/finance_pages.py").read_text(encoding="utf-8")
        tpl = Path("app/web/templates/finance.html").read_text(encoding="utf-8")
        self.assertIn("diagnose_order_delivery", pages)
        self.assertIn("delivery_diag_by_order", pages)
        self.assertIn("delivery_diag_by_order", tpl)
        self.assertIn("تشخیص", tpl)

    def test_backup_env_clarity_bot_and_web(self):
        from app.bot.handlers.admin_backup import _hub_text
        from app.services.users import DEFAULT_SETTINGS

        backups = [{"id": "b1", "size_human": "1 MB", "app_version": "1", "include_env": True}]
        bot = _hub_text(backups, dict(DEFAULT_SETTINGS))
        web = Path("app/web/templates/_settings_backup.html").read_text(encoding="utf-8")
        self.assertIn("شامل .env", bot)
        self.assertIn("بدون .env", bot)
        self.assertIn("همه فروشگاه‌ها", bot)
        self.assertIn("شامل .env", web)
        self.assertIn("بدون .env", web)
        self.assertIn("همه فروشگاه‌ها", web)


class PayrevResendPathTests(unittest.TestCase):
    """approved_resend must resend Telegram — never call approve_payment."""

    def test_resend_path_skips_approve_payment(self):
        src = Path("app/services/payment_review_actions.py").read_text(encoding="utf-8")
        start = src.index("async def execute_payment_resend")
        end = src.index("\nasync def execute_payment_legacy_ok", start)
        block = src[start:end]
        self.assertIn("send_delivery_to_user", block)
        self.assertNotIn("approve_payment(", block)
        self.assertIn("resolve_delivery_failure", block)
        self.assertIn('allows_action("resend")', block)


if __name__ == "__main__":
    unittest.main()
