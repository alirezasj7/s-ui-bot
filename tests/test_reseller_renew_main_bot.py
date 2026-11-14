"""Shop owners can renew capacity on the platform (owner) bot."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class CapacityActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_bot_shop_owner_is_capacity_actor(self):
        from app.services.reseller_access import load_reseller_capacity_actor

        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        profile = SimpleNamespace(is_active=True, user_id=5, plan_id=1)
        with patch(
            "app.services.reseller_access.get_reseller_profile",
            new=AsyncMock(return_value=profile),
        ):
            owner_id, got = await load_reseller_capacity_actor(
                MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
            )
        self.assertEqual(owner_id, 5)
        self.assertIs(got, profile)

    async def test_main_bot_non_reseller_has_no_capacity_actor(self):
        from app.services.reseller_access import load_reseller_capacity_actor

        user = SimpleNamespace(id=9, role="user", telegram_id=777)
        owner_id, profile = await load_reseller_capacity_actor(
            MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
        )
        self.assertIsNone(owner_id)
        self.assertIsNone(profile)

    async def test_main_bot_panel_actor_still_none(self):
        """Full shop panel must stay dedicated-bot only."""
        from app.services.reseller_access import resolve_reseller_owner_id

        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        owner = await resolve_reseller_owner_id(
            MagicMock(), user, is_reseller_bot=False, reseller_owner_id=None
        )
        self.assertIsNone(owner)

    async def test_shop_bot_still_uses_panel_actor(self):
        from app.services.reseller_access import load_reseller_capacity_actor

        user = SimpleNamespace(id=5, role="reseller", telegram_id=100)
        profile = SimpleNamespace(is_active=True, user_id=5)
        with patch(
            "app.services.reseller_access.load_reseller_actor",
            new=AsyncMock(return_value=(5, profile)),
        ) as load:
            owner_id, got = await load_reseller_capacity_actor(
                MagicMock(), user, is_reseller_bot=True, reseller_owner_id=5
            )
        self.assertEqual(owner_id, 5)
        self.assertIs(got, profile)
        load.assert_awaited_once()


class MainBotCapacityKeyboardTests(unittest.TestCase):
    def test_main_keyboard_has_single_reseller_hub_entry(self):
        from app.bot.keyboards import _reply_user_entries

        plan = MagicMock(plan_kind="subscription", allow_buy_extra=False, billing_mode="fixed")
        profile = MagicMock(plan=plan, billing_mode="fixed")
        with patch("app.services.authz.shop_feature_allowed", return_value=True):
            labels = [
                t
                for _, t in _reply_user_entries(
                    "user",
                    has_services=False,
                    ui={},
                    show_reseller_creds=True,
                    profile=profile,
                )
            ]
        self.assertIn("🤝 پنل نماینده", labels)
        self.assertNotIn("🔄 تمدید سرویس", labels)
        self.assertNotIn("🔐 اطلاعات ورود پنل و ربات", labels)

    def test_capacity_entries_hidden_without_creds(self):
        from app.bot.keyboards import _reply_user_entries

        plan = MagicMock(plan_kind="subscription", allow_buy_extra=False, billing_mode="fixed")
        profile = MagicMock(plan=plan)
        labels = [
            t
            for _, t in _reply_user_entries(
                "user",
                has_services=False,
                ui={},
                show_reseller_creds=False,
                profile=profile,
            )
        ]
        self.assertNotIn("🔄 تمدید سرویس", labels)

    def test_reply_action_map_registers_renew_on_main(self):
        from app.bot.keyboards import reply_action_map

        plan = MagicMock(plan_kind="subscription", allow_buy_extra=False, billing_mode="fixed")
        profile = MagicMock(plan=plan)
        mapping = reply_action_map(
            "user",
            has_services=False,
            ui={},
            show_reseller_creds=True,
            is_reseller_bot=False,
            profile=profile,
        )
        self.assertEqual(mapping.get("🔄 تمدید سرویس"), "res_renew")

    def test_soft_reseller_allows_capacity_on_main(self):
        from pathlib import Path

        src = Path("app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        self.assertIn("_RESELLER_CAPACITY_ACTIONS", src)
        self.assertIn("load_reseller_capacity_actor", src)
        self.assertIn('action not in _RESELLER_CAPACITY_ACTIONS', src)

    def test_capacity_context_uses_capacity_actor(self):
        from pathlib import Path

        src = Path("app/bot/handlers/reseller.py").read_text(encoding="utf-8")
        block = src.split("async def _capacity_context")[1].split("async def ")[0]
        self.assertIn("load_reseller_capacity_actor", block)
        self.assertNotIn("await _actor(", block)


if __name__ == "__main__":
    unittest.main()
