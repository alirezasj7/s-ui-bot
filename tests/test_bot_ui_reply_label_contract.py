"""Every reply-keyboard button keeps working, including labels from older releases.

Telegram sends only the pressed button's text, and a customer's phone keeps the
last keyboard until the bot sends a new one. These tests press each visible
button through the real ``ReplyMenuTextFilter`` at the navigation level where
the keyboard is shown and check that it resolves to an action.

``fixtures/bot_ui/reply_labels.json`` is an append-only contract: every label
that ever appeared stays recorded with its action, so renaming a button without
keeping the old text as an alias fails here. Regenerating with
``UPDATE_BOT_UI_SNAPSHOTS=1`` adds new labels and never drops old ones; remove
an entry by hand only when its feature is deliberately removed.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import keyboards as kb
from app.bot import menu_nav as nav
from app.bot.handlers import reply_nav
from tests.bot_ui_snapshots import (
    load_snapshot,
    reply_buttons,
    update_requested,
    write_snapshot,
)
from tests.test_bot_ui_keyboard_snapshots import (
    all_scenarios,
    default_ui,
    sample_reseller_profile,
    status_enabled_ui,
)

CONTRACT_NAME = "reply_labels"
_SHOP_OWNER_ID = 5


@dataclass(frozen=True, slots=True)
class NavScenario:
    """Who is pressing, where they are, and which keyboards they can see there."""

    name: str
    role: str
    level: str
    keyboards: tuple[str, ...]
    is_reseller_bot: bool = False
    show_reseller_creds: bool = False
    state_data: dict[str, str] = field(default_factory=dict)
    status_button_on: bool = False


SCENARIOS: tuple[NavScenario, ...] = (
    NavScenario("user.main", "user", nav.NAV_MAIN, ("reply.main.user_with_services",)),
    NavScenario("user.main_new", "user", nav.NAV_MAIN, ("reply.main.user_new",)),
    NavScenario(
        "user.main_with_status",
        "user",
        nav.NAV_MAIN,
        ("reply.main.user_with_status",),
        status_button_on=True,
    ),
    NavScenario("user.shop", "user", nav.NAV_SHOP, ("reply.shop",)),
    NavScenario("user.wallet", "user", nav.NAV_WALLET, ("reply.wallet",)),
    NavScenario("user.support", "user", nav.NAV_SUPPORT, ("reply.support",)),
    NavScenario("user.loyalty", "user", nav.NAV_LOYALTY, ("reply.loyalty",)),
    NavScenario("user.service", "user", nav.NAV_SERVICE, ("reply.service_actions",)),
    NavScenario("user.pay", "user", nav.NAV_PAY, ("reply.pay",)),
    NavScenario("user.topup_pay", "user", nav.NAV_TOPUP_PAY, ("reply.topup_pay",)),
    NavScenario("user.reseller_apply", "user", nav.NAV_RESELLER_APPLY, ("reply.reseller_apply",)),
    NavScenario(
        "user.submenu_chrome",
        "user",
        nav.NAV_WALLET,
        ("reply.submenu_chrome", "reply.persistent", "reply.cancel"),
    ),
    NavScenario(
        "shop_owner.main_bot",
        "user",
        nav.NAV_MAIN,
        ("reply.main.shop_owner_on_main_bot",),
        show_reseller_creds=True,
    ),
    NavScenario("admin.main", "admin", nav.NAV_MAIN, ("reply.main.admin",)),
    NavScenario("admin.preview", "admin", nav.NAV_USER_PREVIEW, ("reply.main.admin_preview",)),
    NavScenario("admin.hub", "admin", nav.NAV_ADMIN, ("reply.admin.hub",)),
    NavScenario("admin.ops", "admin", nav.NAV_ADMIN_OPS, ("reply.admin.ops",)),
    NavScenario(
        "admin.people",
        "admin",
        nav.NAV_ADMIN_PEOPLE,
        ("reply.admin.people", "reply.admin.people_without_representatives"),
    ),
    NavScenario("admin.product", "admin", nav.NAV_ADMIN_PRODUCT, ("reply.admin.product",)),
    NavScenario("admin.marketing", "admin", nav.NAV_ADMIN_MARKETING, ("reply.admin.marketing",)),
    NavScenario("admin.system", "admin", nav.NAV_ADMIN_SYSTEM, ("reply.admin.system",)),
    NavScenario(
        "admin.pg", "admin", nav.NAV_ADMIN_PG, ("reply.admin.pg", "reply.admin.pg_read_only")
    ),
    NavScenario("admin.users", "admin", nav.NAV_ADMIN_USERS, ("reply.admin.users",)),
    NavScenario("admin.resellers", "admin", nav.NAV_ADMIN_RESELLERS, ("reply.admin.resellers",)),
    NavScenario("admin.settings", "admin", nav.NAV_ADMIN_SETTINGS, ("reply.admin.settings",)),
    NavScenario("admin.backup", "admin", nav.NAV_ADMIN_BACKUP, ("reply.admin.backup",)),
    NavScenario("admin.broadcast", "admin", nav.NAV_ADMIN_BROADCAST, ("reply.admin.broadcast",)),
    NavScenario("admin.loyalty", "admin", nav.NAV_ADMIN_LOYALTY, ("reply.admin.loyalty",)),
    NavScenario(
        "admin.plans_audience",
        "admin",
        nav.NAV_ADMIN_PLANS_AUDIENCE,
        ("reply.admin.plans_audience",),
    ),
    NavScenario(
        "admin.plans_kind_users",
        "admin",
        nav.NAV_ADMIN_PLANS_KIND,
        ("reply.admin.plans_kind_users",),
        state_data={"_adm_plans_aud": "users"},
    ),
    NavScenario(
        "admin.plans_kind_resellers",
        "admin",
        nav.NAV_ADMIN_PLANS_KIND,
        ("reply.admin.plans_kind_resellers",),
        state_data={"_adm_plans_aud": "resellers"},
    ),
    NavScenario(
        "admin.plans_add_users",
        "admin",
        nav.NAV_ADMIN_PLANS_ADD_TYPE,
        ("reply.admin.plans_add_users",),
        state_data={"_adm_plans_aud": "users"},
    ),
    NavScenario(
        "admin.plans_add_resellers",
        "admin",
        nav.NAV_ADMIN_PLANS_ADD_TYPE,
        ("reply.admin.plans_add_resellers",),
        state_data={"_adm_plans_aud": "resellers"},
    ),
    NavScenario("admin.review", "admin", nav.NAV_REVIEW, ("reply.review",)),
    NavScenario(
        "reseller.main", "reseller", nav.NAV_MAIN, ("reply.main.reseller",), is_reseller_bot=True
    ),
    NavScenario(
        "reseller.hub", "reseller", nav.NAV_RESELLER, ("reply.reseller.hub",), is_reseller_bot=True
    ),
    NavScenario(
        "reseller.plans",
        "reseller",
        nav.NAV_RESELLER_PLANS,
        ("reply.reseller.plans",),
        is_reseller_bot=True,
    ),
    NavScenario(
        "reseller.settings",
        "reseller",
        nav.NAV_RESELLER_SETTINGS,
        ("reply.reseller.settings",),
        is_reseller_bot=True,
    ),
)


async def _press(scenario: NavScenario, text: str) -> str | None:
    """Run the production reply filter for *text* and return the resolved action."""
    ui = status_enabled_ui() if scenario.status_button_on else default_ui()
    profile = sample_reseller_profile()
    state = FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1)
    )
    await state.set_data({nav.NAV_LEVEL: scenario.level, **scenario.state_data})
    message = MagicMock()
    message.text = text
    nav_context = (ui, scenario.role, True, scenario.show_reseller_creds)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(reply_nav, "_nav_context", AsyncMock(return_value=nav_context))
        )
        stack.enter_context(
            patch(
                "app.services.reseller_access.load_reseller_actor",
                AsyncMock(return_value=(None, profile)),
            )
        )
        stack.enter_context(
            patch("app.services.resellers.get_reseller_profile", AsyncMock(return_value=profile))
        )
        stack.enter_context(
            patch(
                "app.services.representative_unification.shop_bot_can_manage_representatives",
                AsyncMock(return_value=True),
            )
        )
        result = await reply_nav.ReplyMenuTextFilter()(
            message,
            MagicMock(),
            MagicMock(id=1),
            state,
            is_reseller_bot=scenario.is_reseller_bot,
            reseller_owner_id=_SHOP_OWNER_ID if scenario.is_reseller_bot else None,
        )
    return result["reply_action"] if result else None


def _visible_labels(scenario: NavScenario) -> list[str]:
    builders = all_scenarios()
    labels: list[str] = []
    for keyboard in scenario.keyboards:
        for button in reply_buttons(builders[keyboard]()):
            if button.text not in labels:
                labels.append(button.text)
    return labels


async def _current_contract() -> dict[str, dict[str, str | None]]:
    contract: dict[str, dict[str, str | None]] = {}
    for scenario in SCENARIOS:
        contract[scenario.name] = {
            label: await _press(scenario, label) for label in _visible_labels(scenario)
        }
    return contract


def _merge_contract(
    recorded: dict[str, dict[str, str | None]], current: dict[str, dict[str, str | None]]
) -> dict[str, dict[str, str | None]]:
    merged = {name: dict(labels) for name, labels in recorded.items()}
    for name, labels in current.items():
        merged.setdefault(name, {}).update(labels)
    return merged


class ReplyLabelContractTests(unittest.TestCase):
    def test_every_visible_reply_button_resolves(self) -> None:
        current = asyncio.run(_current_contract())
        for scenario_name, labels in current.items():
            for label, action in labels.items():
                with self.subTest(scenario=scenario_name, label=label):
                    if kb.is_cancel_text(label):
                        # Cancel is consumed by the FSM cancel handler, not the menu filter.
                        self.assertIsNone(action)
                    else:
                        self.assertIsNotNone(action)

    def test_recorded_labels_keep_their_action(self) -> None:
        current = asyncio.run(_current_contract())
        if update_requested():
            write_snapshot(CONTRACT_NAME, _merge_contract(load_snapshot(CONTRACT_NAME), current))
            return
        recorded = load_snapshot(CONTRACT_NAME)
        self.assertTrue(recorded, "missing reply_labels.json; run with UPDATE_BOT_UI_SNAPSHOTS=1")
        by_name = {scenario.name: scenario for scenario in SCENARIOS}
        for scenario_name, labels in recorded.items():
            scenario = by_name.get(scenario_name)
            with self.subTest(scenario=scenario_name):
                self.assertIsNotNone(scenario, "scenario removed from SCENARIOS")
            if scenario is None:
                continue
            for label, action in labels.items():
                with self.subTest(scenario=scenario_name, label=label):
                    self.assertEqual(asyncio.run(_press(scenario, label)), action)

    def test_new_visible_labels_are_recorded(self) -> None:
        if update_requested():
            return
        recorded = load_snapshot(CONTRACT_NAME)
        current = asyncio.run(_current_contract())
        for scenario_name, labels in current.items():
            for label in labels:
                with self.subTest(scenario=scenario_name, label=label):
                    self.assertIn(label, recorded.get(scenario_name, {}))


if __name__ == "__main__":
    unittest.main()
