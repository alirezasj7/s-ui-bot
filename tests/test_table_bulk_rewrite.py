"""Bulk ops rewrite: eligible-only, panel confirm, tab-preserving redirects."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from app.db.models import OrderStatus, PaymentStatus
from app.services.table_bulk import order_bulk_ops, redirect_bulk, sanitize_return_to


ROOT = Path(__file__).resolve().parents[1]


class SanitizeReturnToTests(unittest.TestCase):
    def test_preserves_finance_tab(self):
        out = sanitize_return_to("/finance?tab=orders&q=foo", default="/finance")
        parts = urlsplit(out)
        self.assertEqual(parts.path, "/finance")
        q = parse_qs(parts.query)
        self.assertEqual(q.get("tab"), ["orders"])
        self.assertEqual(q.get("q"), ["foo"])
        self.assertNotIn("ok", q)
        self.assertNotIn("err", q)
        self.assertNotIn("_", q)

    def test_strips_flash_params(self):
        out = sanitize_return_to(
            "/finance?tab=payments&ok=done&err=x&_=123", default="/finance"
        )
        q = parse_qs(urlsplit(out).query)
        self.assertEqual(q.get("tab"), ["payments"])
        self.assertNotIn("ok", q)
        self.assertNotIn("err", q)
        self.assertNotIn("_", q)

    def test_rejects_open_redirect(self):
        self.assertEqual(
            sanitize_return_to("//evil.example/x", default="/users"), "/users"
        )
        self.assertEqual(
            sanitize_return_to("https://evil.example", default="/users"), "/users"
        )

    def test_redirect_bulk_keeps_existing_query(self):
        resp = redirect_bulk("/finance?tab=delivery", ok="۳ تحویل")
        loc = resp.headers["location"]
        self.assertTrue(loc.startswith("/finance?tab=delivery&"))
        self.assertIn("ok=", loc)
        self.assertEqual(loc.count("?"), 1)


class OrderBulkOpsTests(unittest.TestCase):
    def test_pending_payment_full_set(self):
        order = SimpleNamespace(status=OrderStatus.PAID.value)
        pay = SimpleNamespace(status=PaymentStatus.PENDING.value)
        self.assertEqual(order_bulk_ops(order, pay), {"approve", "reject", "cancel"})

    def test_paid_only_approve(self):
        order = SimpleNamespace(status=OrderStatus.PAID.value)
        self.assertEqual(order_bulk_ops(order, None), {"approve"})

    def test_rejected_only_cancel(self):
        order = SimpleNamespace(status=OrderStatus.REJECTED.value)
        self.assertEqual(order_bulk_ops(order, None), {"cancel"})

    def test_delivered_empty(self):
        order = SimpleNamespace(status=OrderStatus.DELIVERED.value)
        self.assertEqual(order_bulk_ops(order, None), set())


class BulkUiContractTests(unittest.TestCase):
    def test_macros_count_badge(self):
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertIn("table-bulk-op-count", macros)
        self.assertIn("data-bulk-op-count", macros)
        self.assertIn("hidden", macros.split("data-bulk-op")[1][:200])

    def test_panel_js_uses_panel_confirm_and_eligible(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        # Scope to the bulk IIFE only — later page scripts may use window.confirm.
        bulk = js.split("Table bulk row selection")[1].split("Capsule numeric steppers")[0]
        self.assertIn("panelConfirm", bulk)
        self.assertIn("eligibleIds", bulk)
        self.assertIn("data-bulk-ops", bulk)
        self.assertIn("cleanReturnTo", bulk)
        self.assertIn("panelSubmitFormPost", bulk)
        self.assertNotIn("showConfirmModal", bulk)
        self.assertNotIn("window.confirm", bulk)

    def test_templates_declare_bulk_ops(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        finance = (ROOT / "app/web/templates/finance.html").read_text(encoding="utf-8")
        tickets = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertIn("data-bulk-ops=", users)
        self.assertIn("data-bulk-ops=", finance)
        self.assertIn("data-bulk-ops=", tickets)
        self.assertIn("/finance/delivery/bulk-action", finance)
        self.assertIn('data-bulk-ops="retry"', finance)

    def test_extended_tables_have_bulk(self):
        files = {
            "reseller_applications.html": "/resellers/applications/bulk-action",
            "resellers.html": "/resellers/bulk-action",
            "plans.html": "/plans/bulk-action",
            "broadcast.html": "/broadcast/history/bulk-action",
            "pg_users.html": "/pg/users/bulk-action",
            "pg_hosts.html": "/pg/hosts/bulk-action",
            "pg_templates.html": "/pg/templates/bulk-action",
            "pg_groups.html": "/pg/groups/bulk-action",
            "pg_nodes.html": "/pg/nodes/bulk-action",
        }
        for name, endpoint in files.items():
            src = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
            self.assertIn("data-bulk-select", src, msg=name)
            self.assertIn("table_bulk_bar", src, msg=name)
            self.assertIn(endpoint, src, msg=name)
            self.assertIn("data-bulk-ops", src, msg=name)
        tickets = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertIn("/tickets/panel/bulk-action", tickets)
        plans = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("/resellers/plans/bulk-action", plans)
        gift_codes = (ROOT / "app/web/templates/gift_codes.html").read_text(encoding="utf-8")
        self.assertIn("/plans/gift-codes/bulk-action", gift_codes)
        self.assertIn("data-bulk-select", gift_codes)

    def test_backend_exports(self):
        src = (ROOT / "app/services/table_bulk.py").read_text(encoding="utf-8")
        self.assertIn("def sanitize_return_to", src)
        self.assertIn("def redirect_bulk", src)
        self.assertIn("def order_bulk_ops", src)
        self.assertIn("async def bulk_delete_users", src)
        self.assertIn("async def bulk_renew_users", src)
        self.assertIn("async def bulk_retry_delivery", src)
        ext = (ROOT / "app/services/table_bulk_ext.py").read_text(encoding="utf-8")
        self.assertIn("async def bulk_reseller_app_action", ext)
        self.assertIn("async def bulk_pg_user_action", ext)
        self.assertIn("async def bulk_shop_plan_action", ext)
        pages = (ROOT / "app/api/bulk_pages.py").read_text(encoding="utf-8")
        self.assertIn("/finance/delivery/bulk-action", pages)
        self.assertIn("/pg/users/bulk-action", pages)
        self.assertIn("/resellers/applications/bulk-action", pages)
        self.assertIn("sanitize_return_to", pages)
        self.assertIn("require_pg_perm", pages)
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("findBulkBar", js)


if __name__ == "__main__":
    unittest.main()
