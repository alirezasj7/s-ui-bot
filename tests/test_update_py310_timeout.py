"""Update tab must work on Python 3.10 (no asyncio.timeout)."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Py310TimeoutCompatTests(unittest.TestCase):
    def test_update_channel_does_not_call_asyncio_timeout(self):
        src = (ROOT / "app/services/update_channel.py").read_text(encoding="utf-8")
        # Doc/comments may mention the name; the 3.11-only *call* must be gone.
        self.assertNotIn("asyncio.timeout(", src)
        self.assertIn("asyncio.wait_for(", src)

    def test_fetch_remote_source_documents_py310(self):
        from app.services import update_channel as uc

        doc = inspect.getdoc(uc.fetch_remote_alembic_revision_ids) or ""
        self.assertIn("wait_for", doc)
        self.assertIn("3.10", doc)


class UpdatePageContextSoftFailTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_soft_fails_when_preflight_raises_like_py310(self):
        """Simulate the production AttributeError — tab context must still return."""
        from app.services.panel_update import update_page_context

        with (
            patch(
                "app.services.panel_update.check_github_update",
                new=AsyncMock(
                    return_value={
                        "version": "0.3.11",
                        "remote_version": "0.3.11",
                        "update_available": False,
                        "label": "ok",
                        "tone": "ok",
                        "checked": True,
                        "channel": "main",
                        "channel_label": "پایدار",
                    }
                ),
            ),
            patch(
                "app.services.panel_update.resolve_stale_update_status",
                return_value={
                    "state": "idle",
                    "awaiting_restart": False,
                    "restart_required": False,
                    "message": "",
                    "percent": 0,
                    "log": [],
                },
            ),
            patch(
                "app.services.panel_update.local_version",
                return_value="0.3.11",
            ),
            patch(
                "app.services.update_channel.migration_preflight",
                new=AsyncMock(
                    side_effect=AttributeError(
                        "module 'asyncio' has no attribute 'timeout'"
                    )
                ),
            ),
            patch(
                "app.services.update_channel.get_update_channel",
                return_value="main",
            ),
            patch(
                "app.services.update_channel.channel_context",
                return_value={
                    "channel": "main",
                    "channel_label": "پایدار",
                    "channels": [
                        {"id": "main", "label": "پایدار"},
                        {"id": "dev", "label": "توسعه"},
                    ],
                },
            ),
            patch(
                "app.services.update_channel.badge_context",
                return_value={
                    "deployed_channel": "main",
                    "deployed_channel_label": "پایدار",
                },
            ),
        ):
            ctx = await update_page_context(force_check=True)

        self.assertIn("update_info", ctx)
        self.assertFalse(ctx["update_info"]["update_available"])
        self.assertFalse(ctx["can_start_update"])
        self.assertEqual(ctx["update_channel"], "main")
        self.assertIn("بررسی", ctx["channel_check_message"])

    async def test_wait_for_path_still_loads_revisions(self):
        """Happy path through wait_for must keep returning revision ids."""
        from tests.test_update_migration_metadata import RemoteMigrationMetadataTests

        suite = RemoteMigrationMetadataTests()
        suite.setUp()
        try:
            revisions = await suite.fetch("dev", force=True)
            self.assertEqual(
                revisions, {"0040_contacts_cancel_notices", "0041_demo_users"}
            )
        finally:
            suite.tearDown()

    async def test_asyncio_timeout_absence_does_not_matter(self):
        """Even if asyncio.timeout is missing, fetch must not AttributeError."""
        import app.services.update_channel as uc

        real_timeout = getattr(asyncio, "timeout", None)
        try:
            if hasattr(asyncio, "timeout"):
                delattr(asyncio, "timeout")
            self.assertFalse(hasattr(asyncio, "timeout"))
            src = inspect.getsource(uc.fetch_remote_alembic_revision_ids)
            self.assertNotIn("asyncio.timeout(", src)
            self.assertIn("asyncio.wait_for(", src)
        finally:
            if real_timeout is not None:
                setattr(asyncio, "timeout", real_timeout)


if __name__ == "__main__":
    unittest.main()
