"""Behavioral tests for inbox dismissal filtering and cleanup."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


class InboxDismissalsLogicTests(unittest.TestCase):
    def test_action_center_active_keys_use_counts(self):
        from app.services.inbox_dismissals import _action_center_active_keys

        keys = _action_center_active_keys(
            {
                "pending": 2,
                "failures": 0,
                "tickets": 1,
                "expiring": 0,
                "low_volume": 0,
                "entries": [],
            }
        )
        self.assertTrue(keys["ac:pending"])
        self.assertTrue(keys["ac:tickets"])
        self.assertNotIn("ac:delivery", keys)

    def test_cleanup_skips_when_action_center_not_ok(self):
        from app.services.inbox_dismissals import _alert_active_map

        active = _alert_active_map(
            {
                "action_center_ok": False,
                "action_center": {"pending": 3, "entries": []},
            }
        )
        self.assertNotIn("ac:pending", active)

    def test_cleanup_still_runs_for_non_ac_when_ac_failed(self):
        """AC build failure must not block forever-row cleanup for update/etc."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services import inbox_dismissals as mod

        row_update = SimpleNamespace(
            id=11, alert_key="update", entity_id="", mode=mod.MODE_FOREVER
        )
        row_ac = SimpleNamespace(
            id=22, alert_key="ac:pending", entity_id="", mode=mod.MODE_FOREVER
        )
        deleted_ids: list[int] = []

        async def fake_execute(stmt):
            # SQLAlchemy delete(...).where(id.in_(...)) — capture bound ids
            try:
                wheres = list(stmt._where_criteria)  # type: ignore[attr-defined]
                for w in wheres:
                    right = getattr(w, "right", None)
                    val = getattr(right, "value", None)
                    if val is not None:
                        deleted_ids.extend(list(val))
            except Exception:
                pass
            return MagicMock()

        async def _run():
            session = MagicMock()
            session.execute = AsyncMock(side_effect=fake_execute)
            session.commit = AsyncMock()
            with patch.object(mod, "load_dismissals", AsyncMock(return_value=[row_update, row_ac])):
                await mod.cleanup_resolved_dismissals(
                    session,
                    {"role": "admin", "org_principal_id": 1},
                    {
                        "action_center_ok": False,
                        "update": {"update_available": False},
                        "shop_maintenance": False,
                        "capacity_warn": False,
                        "payg_risk": {},
                        "ticket_alert": None,
                        "action_center": {"pending": 3, "entries": []},
                    },
                )
            self.assertEqual(session.execute.await_count, 1)
            self.assertEqual(session.commit.await_count, 1)
            self.assertIn(11, deleted_ids)
            self.assertNotIn(22, deleted_ids)

        asyncio.run(_run())

    def test_dismiss_route_wires_flash_and_dual_cache(self):
        from pathlib import Path

        src = Path("app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("_flash_from_query", src)
        self.assertIn("invalidate_sidebar_counts", src)
        self.assertIn("sidebar_cache_key", src)
        inbox = Path("app/web/templates/inbox.html").read_text(encoding="utf-8")
        self.assertIn('name="csrf_token"', inbox.split("form-inbox-dismiss-reset")[1][:400])

    def test_forever_dismiss_hides_while_active(self):
        from app.services.inbox_dismissals import MODE_FOREVER, is_dismissed

        row = SimpleNamespace(mode=MODE_FOREVER, dismissed_at=datetime.now(timezone.utc))
        self.assertTrue(is_dismissed(row, alert_active=True))
        self.assertFalse(is_dismissed(row, alert_active=False))

    def test_24h_dismiss_expires(self):
        from app.services.inbox_dismissals import MODE_24H, SNOOZE_HOURS, is_dismissed

        old = datetime.now(timezone.utc) - timedelta(hours=SNOOZE_HOURS + 1)
        row = SimpleNamespace(mode=MODE_24H, dismissed_at=old)
        self.assertFalse(is_dismissed(row, alert_active=True))

    def test_filter_inbox_context_hides_action_center_entry(self):
        from app.services.inbox_dismissals import MODE_FOREVER, filter_inbox_context

        row = SimpleNamespace(
            id=1,
            alert_key="ac:pending",
            entity_id="",
            mode=MODE_FOREVER,
            dismissed_at=datetime.now(timezone.utc),
        )
        ctx = filter_inbox_context(
            {
                "action_center": {
                    "entries": [
                        {
                            "key": "pending",
                            "title": "1 رسید",
                            "detail": "x",
                            "href": "/finance",
                        }
                    ],
                    "has_items": True,
                }
            },
            [row],
        )
        self.assertEqual(ctx["action_center"]["entries"], [])
        self.assertFalse(ctx["action_center"]["has_items"])

    def test_reset_endpoint_wired(self):
        from pathlib import Path

        src = Path("app/api/home_pages.py").read_text(encoding="utf-8")
        inbox = Path("app/web/templates/inbox.html").read_text(encoding="utf-8")
        self.assertIn("/inbox/dismiss/reset", src)
        self.assertIn("clear_staff_dismissals", src)
        self.assertIn("inbox-tools-card", inbox)
        self.assertIn("بازنشانی اعلان‌های مخفی", inbox)

    def test_staff_dismiss_key_candidates(self):
        from app.services.inbox_dismissals import staff_dismiss_key, staff_dismiss_key_candidates

        staff = {"role": "admin", "bot_user_id": 42, "org_principal_id": 7, "username": "owner"}
        keys = staff_dismiss_key_candidates(staff)
        self.assertEqual(staff_dismiss_key(staff), "op:7")
        self.assertIn("op:7", keys)
        self.assertIn("admin:42", keys)
        self.assertIn("admin:owner", keys)
        self.assertIn("admin:p7", keys)

    def test_staff_dismissal_clause_covers_username(self):
        from app.services.inbox_dismissals import _staff_dismissal_clause

        staff = {"role": "admin", "username": "owner", "org_principal_id": 7}
        clause = _staff_dismissal_clause(staff)
        self.assertIsNotNone(clause)


if __name__ == "__main__":
    unittest.main()
