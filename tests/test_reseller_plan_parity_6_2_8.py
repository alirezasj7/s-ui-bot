"""v6.2.8 — PAYG no buy-extra; addon packs no naming/groups; bot+web+API parity."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.billing import BILLING_MODE_PAYG
from app.services.reseller_capacity import plan_allows_buy_extra

ROOT = Path(__file__).resolve().parents[1]
PLANS_HTML = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
EDIT_HTML = (ROOT / "app/web/templates/reseller_plan_edit.html").read_text(encoding="utf-8")
RESELLER_PAGES = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
ADMIN_PLANS = (ROOT / "app/bot/handlers/admin_plans.py").read_text(encoding="utf-8")
KEYBOARDS = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
CAPACITY = (ROOT / "app/services/reseller_capacity.py").read_text(encoding="utf-8")


class PlanAllowsBuyExtraParityTests(unittest.TestCase):
    def test_fixed_subscription_with_flag(self):
        plan = SimpleNamespace(
            allow_buy_extra=True,
            billing_mode="fixed",
            plan_kind="subscription",
        )
        self.assertTrue(plan_allows_buy_extra(plan))

    def test_payg_never_allows(self):
        plan = SimpleNamespace(
            allow_buy_extra=True,
            billing_mode=BILLING_MODE_PAYG,
            plan_kind="subscription",
        )
        self.assertFalse(plan_allows_buy_extra(plan))

    def test_addon_never_allows(self):
        for kind in ("addon_volume", "addon_users"):
            plan = SimpleNamespace(
                allow_buy_extra=True,
                billing_mode="fixed",
                plan_kind=kind,
            )
            self.assertFalse(plan_allows_buy_extra(plan))

    def test_flag_off(self):
        plan = SimpleNamespace(
            allow_buy_extra=False,
            billing_mode="fixed",
            plan_kind="subscription",
        )
        self.assertFalse(plan_allows_buy_extra(plan))


class WebApiPaygStripTests(unittest.TestCase):
    def test_create_form_hides_buy_extra_for_payg(self):
        self.assertIn("reseller-buy-extra-block", PLANS_HTML)
        self.assertIn("!isAddon && !isPayg", PLANS_HTML)
        self.assertIn("خرید حجم/کاربر اضافه لازم نیست", PLANS_HTML)

    def test_edit_hides_buy_extra_for_payg(self):
        self.assertIn("edit-buy-extra-block", EDIT_HTML)
        self.assertIn("payg ||", EDIT_HTML)
        self.assertIn("بدون نام‌گذاری سرویس", EDIT_HTML)

    def test_api_create_strips_payg_extras(self):
        create = RESELLER_PAGES[
            RESELLER_PAGES.find("async def reseller_plan_create") : RESELLER_PAGES.find(
                "async def reseller_plan_edit_page"
            )
        ]
        self.assertIn('allow_buy_extra=bool(form.get("allow_buy_extra")) if billing_mode == "fixed" else False', create)
        self.assertIn('extra_gb_price=_parse_nonneg_int(form, "extra_gb_price") if billing_mode == "fixed" else 0', create)

    def test_api_edit_strips_payg_extras(self):
        edit = RESELLER_PAGES[
            RESELLER_PAGES.find("async def reseller_plan_edit_save") : RESELLER_PAGES.find(
                "async def reseller_plan_toggle"
            )
        ]
        payg_idx = edit.find('if billing_mode == "payg":')
        self.assertGreaterEqual(payg_idx, 0)
        branch = edit[payg_idx : payg_idx + 400]
        self.assertIn("plan.allow_buy_extra = False", branch)
        self.assertIn("plan.extra_gb_price = 0", branch)
        self.assertIn("plan.extra_user_price = 0", branch)

    def test_buy_extra_forces_from_capacity_api_and_ui(self):
        self.assertIn("allow_buy_extra: bool = False", RESELLER_PAGES)
        self.assertIn('return "from_capacity"', RESELLER_PAGES)
        self.assertIn("allow_buy_extra=bool(plan.allow_buy_extra)", RESELLER_PAGES)
        self.assertIn("renewMode.value = 'from_capacity'", PLANS_HTML)
        self.assertIn("fixedOpt.disabled = true", PLANS_HTML)
        self.assertIn("forceCapacity", EDIT_HTML)
        self.assertIn('plan.renew_pricing_mode = "from_capacity"', ADMIN_PLANS)


class BotParityTests(unittest.TestCase):
    def test_bot_addon_kinds_in_add_picker(self):
        self.assertIn("addon_volume", KEYBOARDS)
        self.assertIn("بسته حجم", KEYBOARDS)
        self.assertIn("بسته کاربر", KEYBOARDS)
        self.assertIn("adm:plans:add:resellers:addon_volume", KEYBOARDS)

    def test_bot_buyextra_flag_and_guards(self):
        self.assertIn("buyextra", ADMIN_PLANS)
        self.assertIn("allow_buy_extra", ADMIN_PLANS)
        self.assertIn("خرید حجم/کاربر اضافه فقط برای اشتراک ثابت است", ADMIN_PLANS)
        self.assertIn("extra_gb", ADMIN_PLANS)
        self.assertIn("addon_gb", ADMIN_PLANS)
        self.assertIn("بدون گروه/نقش/نام‌گذاری سرویس", ADMIN_PLANS)

    def test_save_reseller_plan_forces_subscription_no_extras(self):
        start = ADMIN_PLANS.find("async def _save_reseller_plan")
        self.assertGreaterEqual(start, 0)
        fn = ADMIN_PLANS[start : start + 2500]
        self.assertIn('plan_kind="subscription"', fn)
        self.assertIn("allow_buy_extra=False", fn)
        self.assertIn("extra_gb_price=0", fn)

    def test_capacity_service_documents_fixed_only(self):
        self.assertIn("fixed subscription plans only", CAPACITY)
        self.assertIn("BILLING_MODE_PAYG", CAPACITY)


class ResellerMenuBuyExtraTests(unittest.TestCase):
    def test_fixed_shows_buy_extra_payg_hides(self):
        from app.bot.keyboards import _reseller_submenu_entries

        fixed_plan = MagicMock(
            allow_buy_extra=True,
            billing_mode="fixed",
            plan_kind="subscription",
        )
        profile = MagicMock(billing_mode="fixed", plan=fixed_plan)
        with patch("app.services.authz.shop_feature_allowed", return_value=True):
            labels = [t for _, t in _reseller_submenu_entries(profile)]
        self.assertIn("📦 بسته‌های حجم/کاربر", labels)
        self.assertNotIn("📦 خرید حجم اضافه", labels)

        payg_plan = MagicMock(
            allow_buy_extra=True,
            billing_mode=BILLING_MODE_PAYG,
            plan_kind="subscription",
        )
        profile.plan = payg_plan
        profile.billing_mode = BILLING_MODE_PAYG
        with patch("app.services.authz.shop_feature_allowed", return_value=True):
            labels2 = [t for _, t in _reseller_submenu_entries(profile)]
        self.assertNotIn("📦 خرید حجم اضافه", labels2)
        self.assertNotIn("👤 خرید کاربر اضافه", labels2)
        self.assertIn("📦 بسته‌های حجم/کاربر", labels2)


class FormatAddonDetailTests(unittest.TestCase):
    def test_addon_detail_omits_groups_role(self):
        from app.services.resellers import format_reseller_plan_apply_detail

        plan = SimpleNamespace(
            name="بسته ۲۰ گیگ",
            description="تست",
            plan_kind="addon_volume",
            billing_mode="fixed",
            price=50_000,
            addon_gb=20,
            addon_users=0,
            pg_group_ids="1,2",
            pg_role_id=9,
        )
        text = format_reseller_plan_apply_detail(plan, currency="تومان")
        self.assertIn("بسته حجم", text)
        self.assertIn("+20 گیگ", text)
        self.assertIn("نام‌گذاری سرویس", text)
        self.assertNotIn("گروه‌های پاسارگارد", text)
        self.assertNotIn("نقش پاسارگارد", text)


if __name__ == "__main__":
    unittest.main()
