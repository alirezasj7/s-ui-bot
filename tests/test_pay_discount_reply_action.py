"""Pressing the discount button on the payment reply keyboard opens the code prompt."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot import keyboards as kb
from app.bot import menu_nav as nav
from app.bot.handlers import reply_nav
from app.bot.handlers import shop as shop_h


class PayDiscountReplyActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_discount_button_passes_user_to_prompt(self) -> None:
        db_user = SimpleNamespace(id=7)
        order = SimpleNamespace(id=11, user_id=7)
        session = MagicMock()
        session.get = AsyncMock(return_value=order)
        state = MagicMock()
        state.get_data = AsyncMock(return_value={nav.PAY_ORDER_ID: 11})
        bubble = MagicMock()
        message = MagicMock()
        message.answer = AsyncMock(return_value=bubble)
        message.bot = MagicMock()
        message.from_user = SimpleNamespace(id=1)

        with patch.object(shop_h, "ask_discount", new=AsyncMock()) as ask_discount:
            await reply_nav._handle_pay_action(
                message, session, db_user, state, kb.REPLY_ACTION_PAY_DISCOUNT
            )

        ask_discount.assert_awaited_once()
        args = ask_discount.await_args.args
        self.assertIs(args[3], db_user)
        self.assertEqual(args[0].data, "pay:discount:11")


if __name__ == "__main__":
    unittest.main()
