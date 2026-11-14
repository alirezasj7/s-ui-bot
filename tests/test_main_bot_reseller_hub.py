"""Shop owners on the platform bot reach access card, PasarGuard and capacity from one inline hub."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot import keyboards as kb
from app.bot.nav_inline import reseller_main_bot_hub_keyboard


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _subscription_profile() -> MagicMock:
    return MagicMock(plan=MagicMock(plan_kind="subscription", allow_buy_extra=False))


class HubKeyboardTests(unittest.TestCase):
    def test_hub_lists_creds_pg_and_capacity_with_reseller_callbacks(self) -> None:
        with patch(
            "app.services.pg_admin_subscription.is_subscription_plan", return_value=True
        ):
            cbs = _callbacks(
                reseller_main_bot_hub_keyboard(_subscription_profile(), {}, show_pg=True)
            )
        self.assertIn("nv:res:ra:reseller_creds", cbs)
        self.assertIn("nv:adm:pg", cbs)
        self.assertIn("nv:res:ra:res_renew", cbs)
        self.assertIn("nv:res:ra:res_addon_packs", cbs)
        self.assertEqual(cbs[-1], "menu:home")

    def test_pg_button_hidden_without_pg_access(self) -> None:
        cbs = _callbacks(reseller_main_bot_hub_keyboard(None, {}, show_pg=False))
        self.assertNotIn("nv:adm:pg", cbs)
        self.assertIn("nv:res:ra:reseller_creds", cbs)

    def test_callbacks_fit_telegram_limit(self) -> None:
        with patch(
            "app.services.pg_admin_subscription.is_subscription_plan", return_value=True
        ):
            cbs = _callbacks(
                reseller_main_bot_hub_keyboard(_subscription_profile(), {}, show_pg=True)
            )
        self.assertTrue(all(len(c.encode()) <= 64 for c in cbs))


class MainKeyboardTests(unittest.TestCase):
    def test_pg_and_creds_not_on_reply_keyboard_but_still_mapped(self) -> None:
        entries = kb._reply_user_entries(
            "user", has_services=False, ui={}, show_reseller_creds=True
        )
        keys = [k for k, _ in entries]
        self.assertIn(kb.REPLY_ACTION_RESELLER, keys)
        self.assertNotIn(kb.REPLY_ACTION_ADMIN_PG, keys)
        self.assertNotIn(kb.REPLY_ACTION_CREDS, keys)
        mapping = kb.reply_action_map(
            "user", has_services=False, ui={}, show_reseller_creds=True,
            is_reseller_bot=False, profile=None,
        )
        self.assertEqual(mapping.get(kb._t({}, "btn_reseller_creds")), kb.REPLY_ACTION_CREDS)
        self.assertEqual(mapping.get(kb._t({}, "btn_adm_pg")), kb.REPLY_ACTION_ADMIN_PG)

    def test_plain_customer_never_gets_hub_entry(self) -> None:
        keys = [
            k for k, _ in kb._reply_user_entries(
                "user", has_services=False, ui={}, show_reseller_creds=False
            )
        ]
        self.assertNotIn(kb.REPLY_ACTION_RESELLER, keys)


class OpenHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_bot_reseller_gets_inline_hub(self) -> None:
        from app.bot.handlers import reply_nav

        user = SimpleNamespace(id=5, role="reseller", telegram_id=1)
        present = AsyncMock()
        with (
            patch("app.services.reseller_access.load_reseller_capacity_actor",
                  new=AsyncMock(return_value=(5, _subscription_profile()))),
            patch("app.bot.auth.bot_may_open_pg_hub", new=AsyncMock(return_value=True)),
            patch.object(reply_nav, "get_all_settings", new=AsyncMock(return_value={})),
            patch("app.bot.nav_inline.present_nav_panel", new=present),
        ):
            await reply_nav.open_reseller_home(
                MagicMock(), MagicMock(), user, None,
                is_reseller_bot=False, reseller_owner_id=None,
            )
        cbs = _callbacks(present.await_args.kwargs["inline"])
        self.assertIn("nv:adm:pg", cbs)

    async def test_non_reseller_falls_back_to_creds_refusal(self) -> None:
        from app.bot.handlers import reply_nav

        user = SimpleNamespace(id=9, role="user", telegram_id=2)
        creds = AsyncMock()
        present = AsyncMock()
        with (
            patch.object(reply_nav, "open_reseller_creds", new=creds),
            patch("app.bot.nav_inline.present_nav_panel", new=present),
        ):
            await reply_nav.open_reseller_home(
                MagicMock(), MagicMock(), user, None,
                is_reseller_bot=False, reseller_owner_id=None,
            )
        creds.assert_awaited_once()
        present.assert_not_awaited()

    async def test_pg_hub_back_for_main_bot_reseller_returns_to_reseller_hub(self) -> None:
        from app.bot.handlers import reply_nav

        user = SimpleNamespace(id=5, role="reseller", telegram_id=1)
        present = AsyncMock()
        with (
            patch("app.bot.auth.bot_may_open_pg_hub", new=AsyncMock(return_value=True)),
            patch("app.bot.auth.bot_migrated_pg_features",
                  new=AsyncMock(return_value=frozenset({"pg_users"}))),
            patch("app.bot.auth.bot_pg_can_create_user", new=AsyncMock(return_value=False)),
            patch.object(reply_nav, "get_all_settings", new=AsyncMock(return_value={})),
            patch("app.bot.nav_inline.present_nav_panel", new=present),
        ):
            await reply_nav.open_pg_home(
                MagicMock(), MagicMock(), user, None, is_reseller_bot=False
            )
        cbs = _callbacks(present.await_args.kwargs["inline"])
        self.assertIn("nv:res:home", cbs)
        self.assertNotIn("nv:adm:product", cbs)

    async def test_pg_hub_denied_without_pg_features(self) -> None:
        from app.bot.handlers import reply_nav

        user = SimpleNamespace(id=5, role="reseller", telegram_id=1)
        message = MagicMock(answer=AsyncMock())
        present = AsyncMock()
        with (
            patch("app.bot.auth.bot_may_open_pg_hub", new=AsyncMock(return_value=False)),
            patch("app.bot.nav_inline.present_nav_panel", new=present),
        ):
            await reply_nav.open_pg_home(
                message, MagicMock(), user, None, is_reseller_bot=False
            )
        present.assert_not_awaited()
        message.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
