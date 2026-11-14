"""A settings group's warning is shown inside that group's box, right under its title."""

from __future__ import annotations

from tests.test_update_owner_only import OWNER_SESSION, SHOP_SESSION, RoutesHarness

FORCE_JOIN = "ربات باید ادمین کانال باشد"
TERMS = "ایموجی پریمیوم تلگرام"


def _comes_right_after_title(html: str, title: str, notice: str) -> bool:
    """The notice follows the group's <h2> before any field of the group."""
    head = html.find(f"<h2>{title}</h2>")
    at = html.find(f"<strong>{notice}</strong>")
    grid = html.find('class="settings-grid"', head)
    return -1 < head < at < grid


class GroupNoticeTests(RoutesHarness):
    async def _page(self, session: dict, path: str) -> str:
        cookie = f"session={self.signer.dumps(session)}; csrf=token"
        return (await self.client.get(path, headers={"cookie": cookie})).text

    async def test_the_owner_limits_tab_puts_each_warning_in_its_box(self) -> None:
        html = await self._page(OWNER_SESSION, "/settings?tab=limits")
        self.assertTrue(_comes_right_after_title(html, "کانال اجباری", FORCE_JOIN))
        self.assertTrue(_comes_right_after_title(html, "قوانین ورود به ربات", TERMS))
        self.assertEqual(html.count(f"<strong>{FORCE_JOIN}</strong>"), 1)

    async def test_the_shop_limits_tab_does_the_same(self) -> None:
        html = await self._page(SHOP_SESSION, "/shop-settings?tab=limits")
        self.assertTrue(_comes_right_after_title(html, "کانال اجباری", FORCE_JOIN))
        self.assertEqual(html.count(f"<strong>{FORCE_JOIN}</strong>"), 1)
