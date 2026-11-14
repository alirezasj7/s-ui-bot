"""v4.10.9 — force-join status allowlist, inline join buttons, custom msg."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
MW = (ROOT / "app/bot/middlewares.py").read_text(encoding="utf-8")
START = (ROOT / "app/bot/handlers/start.py").read_text(encoding="utf-8")
KB = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
USERS = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")


class NormalizeAndUrlTests(unittest.TestCase):
    def test_username_lowercased_and_invite_rejected_as_id(self):
        from app.services.users import (
            force_join_channel_url,
            normalize_force_join_channel_id,
            parse_force_join_entries,
        )

        self.assertEqual(normalize_force_join_channel_id("https://t.me/MyChan"), "@mychan")
        self.assertEqual(normalize_force_join_channel_id("MyChan"), "@mychan")
        self.assertEqual(normalize_force_join_channel_id("-100123"), "-100123")
        self.assertEqual(normalize_force_join_channel_id("https://t.me/+AbCdEf"), "")
        self.assertEqual(normalize_force_join_channel_id("https://t.me/joinchat/AbCd"), "")

        self.assertEqual(force_join_channel_url("@MyChan"), "https://t.me/mychan")
        self.assertEqual(
            force_join_channel_url("-1001", "https://t.me/+Invite"),
            "https://t.me/+Invite",
        )

        raw = (
            '[{"id":"-1001","required":true,"link":"https://t.me/+x"},'
            '{"id":"@Opt","required":false}]'
        )
        entries = parse_force_join_entries(raw)
        self.assertEqual(entries[0]["id"], "-1001")
        self.assertEqual(entries[0]["link"], "https://t.me/+x")
        self.assertEqual(entries[1]["id"], "@opt")


class MembershipStatusTests(unittest.TestCase):
    def test_joined_statuses_and_restricted(self):
        from app.bot import middlewares as mw

        mw._FORCE_JOIN_MEMBER_CACHE.clear()
        bot = AsyncMock()

        async def _run():
            for status in ("member", "administrator", "creator"):
                member = MagicMock()
                member.status = status
                bot.get_chat_member = AsyncMock(return_value=member)
                self.assertIs(
                    await mw.check_force_join_member(bot, 1, "@chan"), True, status
                )
                mw._FORCE_JOIN_MEMBER_CACHE.clear()

            restricted = MagicMock()
            restricted.status = "restricted"
            restricted.is_member = True
            bot.get_chat_member = AsyncMock(return_value=restricted)
            self.assertIs(await mw.check_force_join_member(bot, 1, "@chan"), True)
            mw._FORCE_JOIN_MEMBER_CACHE.clear()

            restricted.is_member = False
            bot.get_chat_member = AsyncMock(return_value=restricted)
            self.assertIs(await mw.check_force_join_member(bot, 1, "@chan"), False)

            for status in ("left", "kicked"):
                member = MagicMock()
                member.status = status
                bot.get_chat_member = AsyncMock(return_value=member)
                self.assertIs(await mw.check_force_join_member(bot, 1, "@chan"), False)
                mw._FORCE_JOIN_MEMBER_CACHE.clear()

            bot.get_chat_member = AsyncMock(side_effect=RuntimeError("not admin"))
            self.assertIsNone(await mw.check_force_join_member(bot, 1, "@chan"))

            # Invite-only id cannot be verified
            self.assertIsNone(await mw.check_force_join_member(bot, 1, "https://t.me/+x"))

        asyncio.run(_run())

    def test_get_chat_member_receives_int_for_numeric_id(self):
        from app.bot import middlewares as mw

        mw._FORCE_JOIN_MEMBER_CACHE.clear()
        bot = AsyncMock()
        member = MagicMock()
        member.status = "member"
        bot.get_chat_member = AsyncMock(return_value=member)

        async def _run():
            self.assertTrue(await mw.check_force_join_member(bot, 42, "-100999"))
            bot.get_chat_member.assert_awaited_with(-100999, 42)

        asyncio.run(_run())


class MessageAndKeyboardTests(unittest.TestCase):
    def test_unverified_message_differs_from_missing(self):
        from app.bot.middlewares import force_join_block_message

        missing_text = force_join_block_message(["@a"], [])
        unverified_text = force_join_block_message([], ["@a"])
        # Channels live on inline buttons — default copy has no @ bullets
        self.assertNotIn("@a", missing_text)
        self.assertIn("دکمه‌های زیر", missing_text)
        self.assertIn("ادمین", unverified_text)
        custom = force_join_block_message(
            ["@a"], [], custom="join please:\n{channels}"
        )
        self.assertIn("@a", custom)
        self.assertIn("join please", custom)

    def test_inline_keyboard_has_url_and_check(self):
        from app.bot.keyboards import force_join_inline_keyboard

        kb = force_join_inline_keyboard(
            '[{"id":"@News","required":true},{"id":"-1001","required":true,"link":"https://t.me/+z"}]'
        )
        flat = [b for row in kb.inline_keyboard for b in row]
        urls = [b.url for b in flat if b.url]
        cbs = [b.callback_data for b in flat if b.callback_data]
        self.assertIn("https://t.me/news", urls)
        self.assertIn("https://t.me/+z", urls)
        self.assertIn("forcejoin:check", cbs)

    def test_wiring(self):
        self.assertIn("force_join_inline_keyboard", START)
        self.assertIn("forcejoin:check", START)
        self.assertIn("forcejoin:", MW)
        self.assertIn("force_join_msg", USERS)
        self.assertIn("btn_force_join", USERS)
        self.assertIn("_JOINED_STATUSES", MW)
        self.assertIn("is_member", MW)
        self.assertIn("force-channel-link", JS)
        self.assertIn("force_join_inline_keyboard", KB)


if __name__ == "__main__":
    unittest.main()
