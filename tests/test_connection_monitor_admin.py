"""Owner selection, publication and pause rules against fresh synthetic catalogs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from sqlalchemy import func, select

from connection_monitor_support import MonitorDatabaseCase, monitor_access, subscription_fixture_key

from app.bot.connection_status_ui import admin_page_keyboard, admin_page_text, target_text
from app.db.models import ConnectionMonitorSnapshot, ConnectionMonitorState, ConnectionMonitorTarget, OrgPrincipal
from app.services.connection_monitor_actions import edit_monitor_target, select_monitor_config
from app.services.connection_monitor_admin import monitor_config_choices, set_monitor_enabled
from app.services.connection_monitor_subscription import subscription_entries
from app.services.connection_monitor_panel import MonitorCatalog
from app.services.connection_monitor_preferences import MonitorPreferences, delete_monitor_target, pause_monitor_target
from app.services.connection_monitor_views import monitor_admin_page, monitor_target_view
from app.services.users import DEFAULT_SETTINGS


class MonitorAdminTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        fixture = json.loads((Path(__file__).parent / "fixtures/connection_monitor_catalog.json").read_text())
        self.catalog = MonitorCatalog(fixture["native_configs"], checked_at=datetime.now(timezone.utc))
        self.catalog_reader = AsyncMock(return_value=self.catalog)
        for patcher in (
            patch("app.services.connection_monitor_preferences.read_monitor_catalog", self.catalog_reader),
            patch("app.services.connection_monitor_admin.read_monitor_catalog", self.catalog_reader),
            patch("app.services.connection_monitor_admin.reveal_monitor_token", AsyncMock(return_value="synthetic")),
            patch("app.services.connection_monitor_admin.XrayBinary.verify", return_value=Path("/synthetic/xray")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        async with self.Session() as session:
            session.add(ConnectionMonitorState(pg_user_id=900, pg_username="monitor-only", account_revision="one", subscription_token_enc="encrypted"))
            await session.commit()

    async def select_host(self, host_id: int = 41) -> int:
        async with self.Session() as session:
            key = subscription_fixture_key(0 if host_id == 41 else 1) if host_id in (41, 72) else "Z" * 43
            return await select_monitor_config(session, self.access, config_key=key)

    async def test_selection_is_private_and_does_not_hold_a_transaction_across_panel_io(self) -> None:
        async with self.Session() as session:
            async def read(account: object) -> MonitorCatalog:
                self.assertFalse(session.in_transaction())
                return self.catalog
            self.catalog_reader.side_effect = read
            target_id = await select_monitor_config(session, self.access, config_key=subscription_fixture_key())
            self.assertFalse(session.in_transaction())
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertTrue(target.test_enabled)
            self.assertFalse(target.is_public)
            self.assertEqual(target.endpoint_count, 1)
            self.assertTrue(target.generation)
            snapshots = (await session.scalars(select(ConnectionMonitorSnapshot))).all()
            self.assertEqual(len(snapshots), 1)
            self.assertTrue(all(row.status == "unknown" for row in snapshots))

    async def test_name_order_and_publication_preserve_measurement_generation(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            await set_monitor_enabled(session, self.access, enabled=True)
            before = await session.get(ConnectionMonitorTarget, target_id)
            generation = before.generation
            await session.commit()
            for field, value in (("public_name", "  <b>هاست عمومی</b>  "), ("display_order", 12), ("is_public", True)):
                await edit_monitor_target(session, self.access, target_id=target_id, field=field, value=value)
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertEqual(view.public_name, "<b>هاست عمومی</b>")
            self.assertEqual(view.display_order, 12)
            self.assertTrue(view.is_public)
            text = target_text(view)
            self.assertIn("&lt;b&gt;هاست عمومی&lt;/b&gt;", text)
            after = await session.get(ConnectionMonitorTarget, target_id, populate_existing=True)
            self.assertEqual(after.generation, generation)

    async def test_empty_public_name_invalid_numbers_and_hostile_control_text_are_rejected(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            for field, value in (("is_public", True), ("display_order", True), ("display_order", -1),
                                 ("display_order", 2147483648), ("public_name", "x" * 65), ("public_name", "line\nbreak")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    await edit_monitor_target(session, self.access, target_id=target_id, field=field, value=value)
        for host_id in (True, 0, -1, "41", 2147483648):
            with self.subTest(host_id=host_id), self.assertRaises(ValidationError):
                MonitorPreferences(config_key=host_id)

    async def test_stale_picker_cannot_select_a_now_disabled_missing_or_unsupported_host(self) -> None:
        self.catalog.native_configs[0]["outbounds"][0]["protocol"] = "blackhole"
        with self.assertRaises(ValueError):
            await self.select_host()
        with self.assertRaises(ValueError):
            await self.select_host(999)
        self.catalog.native_configs[0]["outbounds"][0]["protocol"] = "vless"
        self.catalog.native_configs[0]["outbounds"][0]["streamSettings"]["security"] = "none"
        with self.assertRaises(ValueError):
            await self.select_host()
        async with self.Session() as session:
            self.assertIsNone(await session.scalar(select(ConnectionMonitorTarget.id).limit(1)))

    async def test_owner_revoked_during_panel_read_cannot_select_or_publish(self) -> None:
        async def revoke(account: object) -> MonitorCatalog:
            async with self.Session() as other:
                owner = await other.get(OrgPrincipal, 1)
                owner.status = "disabled"
                await other.commit()
            return self.catalog
        self.catalog_reader.side_effect = revoke
        with self.assertRaises(ValueError):
            await self.select_host()
        async with self.Session() as session:
            self.assertIsNone(await session.scalar(select(ConnectionMonitorTarget.id).limit(1)))

    async def test_pause_works_without_panel_and_reselect_never_republishes(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            await set_monitor_enabled(session, self.access, enabled=True)
            await edit_monitor_target(session, self.access, target_id=target_id, field="public_name", value="عمومی")
            await edit_monitor_target(session, self.access, target_id=target_id, field="is_public", value=True)
            self.catalog_reader.reset_mock()
            await pause_monitor_target(session, self.access, target_id=target_id)
            self.catalog_reader.assert_not_called()
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertFalse(view.test_enabled)
            self.assertFalse(view.is_public)
            self.assertEqual(view.health.status, "paused")
        await self.select_host()
        async with self.Session() as session:
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertTrue(view.test_enabled)
            self.assertFalse(view.is_public)
            self.assertEqual(view.public_name, "عمومی")

    async def test_delete_removes_local_target_and_snapshots_without_panel_io(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            await set_monitor_enabled(session, self.access, enabled=True)
            await edit_monitor_target(session, self.access, target_id=target_id, field="public_name", value="عمومی")
            await edit_monitor_target(session, self.access, target_id=target_id, field="is_public", value=True)
            self.assertGreater(await session.scalar(select(func.count()).select_from(ConnectionMonitorSnapshot)), 0)
            self.catalog_reader.reset_mock()
            await delete_monitor_target(session, self.access, target_id=target_id)
            self.catalog_reader.assert_not_called()
            self.assertIsNone(await session.get(ConnectionMonitorTarget, target_id))
            self.assertEqual(await session.scalar(select(func.count()).select_from(ConnectionMonitorSnapshot)), 0)
            with self.assertRaises(ValueError):
                await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            with self.assertRaises(ValueError):
                await delete_monitor_target(session, self.access, target_id=target_id)

    async def test_wrong_shop_and_customer_cannot_read_or_mutate_private_targets(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            session.add(ConnectionMonitorTarget(id=999, reseller_id=2, pg_host_id=72, test_enabled=True))
            await session.commit()
            for invalid_id in (999, True, -1):
                with self.subTest(target_id=invalid_id), self.assertRaises(ValueError):
                    await pause_monitor_target(session, self.access, target_id=invalid_id)
                with self.subTest(delete_id=invalid_id), self.assertRaises(ValueError):
                    await delete_monitor_target(session, self.access, target_id=invalid_id)
            customer = monitor_access(role="customer", org_principal_id=None)
            with self.assertRaises(ValueError):
                await monitor_target_view(session, customer, target_id=target_id, now=self.now)
            with self.assertRaises(ValueError):
                await edit_monitor_target(session, customer, target_id=target_id, field="public_name", value="other")
            with self.assertRaises(ValueError):
                await delete_monitor_target(session, customer, target_id=target_id)
            self.assertIsNotNone(await session.get(ConnectionMonitorTarget, target_id))
            self.assertIsNotNone(await session.get(ConnectionMonitorTarget, 999))

    async def test_runtime_pause_unpublishes_and_invalidates_evidence_and_repeated_start_is_idempotent(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            await set_monitor_enabled(session, self.access, enabled=True)
            await edit_monitor_target(session, self.access, target_id=target_id, field="public_name", value="عمومی")
            await edit_monitor_target(session, self.access, target_id=target_id, field="is_public", value=True)
            await set_monitor_enabled(session, self.access, enabled=True)
            target = await session.get(ConnectionMonitorTarget, target_id, populate_existing=True)
            self.assertTrue(target.is_public)
            await session.commit()
            await set_monitor_enabled(session, self.access, enabled=False)
            target = await session.get(ConnectionMonitorTarget, target_id, populate_existing=True)
            state = await session.scalar(select(ConnectionMonitorState))
            self.assertFalse(target.is_public)
            self.assertFalse(state.enabled)
            self.assertIsNone(state.catalog_synced_at)
            self.assertIsNone(state.cycle_token)

    async def test_active_picker_is_bounded_and_admin_keyboard_callbacks_are_valid(self) -> None:
        self.catalog.native_configs.extend({**self.catalog.native_configs[1], "remarks": f"کانفیگ {index}"} for index in range(100, 115))
        self.catalog.native_configs[0]["outbounds"][0]["protocol"] = "blackhole"
        async with self.Session() as session:
            page = await monitor_config_choices(session, self.access)
            self.assertEqual(len(page.choices), 10)
            self.assertIsNotNone(page.choices[0].issue)
            self.assertEqual([choice.position for choice in page.choices], list(range(10)))
            self.assertIsNotNone(page.next_offset)
            overview = await monitor_admin_page(session, self.access, now=self.now)
        text = admin_page_text(overview, dict(DEFAULT_SETTINGS))
        self.assertIn("بررسی از سرور ربات", text)
        self.assertNotIn("encrypted", text)
        markup = admin_page_keyboard(overview)
        self.assertTrue(all(len(button.callback_data.encode()) <= 64 for row in markup.inline_keyboard for button in row))

    async def test_effective_endpoint_capacity_prevents_selection_without_partial_rows(self) -> None:
        self.catalog.native_configs[:] = [{**self.catalog.native_configs[0], "remarks": f"config {index}"} for index in range(13)]
        keys = [entry.config_key for entry in subscription_entries(self.catalog.native_configs)]
        async with self.Session() as session:
            session.add_all(ConnectionMonitorTarget(subscription_key=key, test_enabled=True) for key in keys[:12])
            await session.commit()
        with self.assertRaises(ValueError):
            async with self.Session() as session:
                await select_monitor_config(session, self.access, config_key=keys[12])
        async with self.Session() as session:
            self.assertIsNone(await session.scalar(select(ConnectionMonitorTarget.id).where(ConnectionMonitorTarget.subscription_key == keys[12]).limit(1)))

    async def test_selection_changed_while_waiting_for_catalog_requires_a_fresh_retry(self) -> None:
        async def concurrent_selection(account: object) -> MonitorCatalog:
            async with self.Session() as other:
                other.add(ConnectionMonitorTarget(subscription_key=subscription_fixture_key(1), test_enabled=True))
                await other.commit()
            return self.catalog
        self.catalog_reader.side_effect = concurrent_selection
        with self.assertRaises(ValueError):
            await self.select_host()
        async with self.Session() as session:
            config_keys = (await session.scalars(select(ConnectionMonitorTarget.subscription_key))).all()
            self.assertEqual(config_keys, [subscription_fixture_key(1)])

    async def test_publication_requires_the_runtime_to_be_enabled(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            await edit_monitor_target(session, self.access, target_id=target_id, field="public_name", value="عمومی")
            with self.assertRaises(ValueError):
                await edit_monitor_target(session, self.access, target_id=target_id, field="is_public", value=True)
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertFalse(target.is_public)

    async def test_private_diagnostics_keep_last_check_time_and_only_show_known_safe_reasons(self) -> None:
        target_id = await self.select_host()
        async with self.Session() as session:
            state = await session.scalar(select(ConnectionMonitorState))
            state.enabled, state.catalog_synced_at = True, self.now
            rows = (await session.scalars(select(ConnectionMonitorSnapshot))).all()
            for row in rows:
                row.status, row.checked_at = "healthy", self.now - timedelta(seconds=180)
            await session.commit()
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertEqual((view.health.status, view.reason), ("unknown", "stale"))
            self.assertIsNotNone(view.health.checked_at)
            self.assertIn("نتیجه قدیمی", target_text(view))
            for row in rows:
                row.status, row.checked_at, row.reason = "unknown", self.now, "core_unavailable"
            await session.commit()
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertIn("Xray آماده نیست", target_text(view))
            for row in rows:
                row.reason = "sensitive-token"
            await session.commit()
            view = await monitor_target_view(session, self.access, target_id=target_id, now=self.now)
            self.assertNotIn("sensitive", target_text(view))
            self.assertIsNone(view.reason)
