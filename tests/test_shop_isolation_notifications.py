"""A customer is notified through the bot of the shop the message is about."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import reseller_bots
from app.services.payer_notify import notify_payer
from app.services.reseller_bots import ATTRIBUTED_SHOP, open_notify_bot_for_user

ATTRIBUTED_TO = 5


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[int] = []
        self.session = SimpleNamespace(close=AsyncMock())

    async def send_message(self, chat_id: int, *_args, **_kwargs) -> None:
        self.sent.append(chat_id)


class NotifyBotChoiceTests(unittest.IsolatedAsyncioTestCase):
    async def chosen_shop(self, **kwargs) -> int | None:
        user = SimpleNamespace(reseller_id=ATTRIBUTED_TO, telegram_id=1)
        asked: list[int] = []

        async def for_reseller(_session, rid):
            asked.append(int(rid))
            return FakeBot(), False

        with (
            patch.object(reseller_bots, "open_notify_bot_for_reseller", for_reseller),
            patch("app.bot.create_bot", return_value=FakeBot()),
        ):
            await open_notify_bot_for_user(MagicMock(), user, **kwargs)
        return asked[0] if asked else None

    async def test_without_a_shop_the_attributed_shops_bot_is_used(self):
        self.assertEqual(await self.chosen_shop(), ATTRIBUTED_TO)

    async def test_the_shop_of_the_message_wins_over_attribution(self):
        self.assertEqual(await self.chosen_shop(shop_id=9), 9)

    async def test_a_platform_message_never_uses_the_attributed_shops_bot(self):
        self.assertIsNone(await self.chosen_shop(shop_id=None))


class PayerNotifyTests(unittest.IsolatedAsyncioTestCase):
    async def used_shop(self, **kwargs):
        seen: dict = {}

        async def opener(_session, _user, *, shop_id=ATTRIBUTED_SHOP):
            seen["shop_id"] = shop_id
            return FakeBot(), False

        session = MagicMock()
        session.get = AsyncMock(return_value=SimpleNamespace(telegram_id=1, reseller_id=ATTRIBUTED_TO))
        with patch.object(reseller_bots, "open_notify_bot_for_user", opener):
            sent = await notify_payer(session, 1, title="t", body="b", **kwargs)
        return sent, seen.get("shop_id")

    async def test_the_orders_shop_is_passed_to_the_bot_choice(self):
        sent, shop = await self.used_shop(shop_id=9)
        self.assertTrue(sent)
        self.assertEqual(shop, 9)

    async def test_a_platform_order_is_passed_as_the_platform(self):
        _sent, shop = await self.used_shop(shop_id=None)
        self.assertIsNone(shop)

    async def test_without_a_shop_the_default_marker_is_passed(self):
        _sent, shop = await self.used_shop()
        self.assertIs(shop, ATTRIBUTED_SHOP)
