"""The PasarGuard hub must send resellers back to their own home, not an owner-only screen."""
from __future__ import annotations

import unittest

from app.bot.nav_inline import pg_hub_keyboard


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


class PgHubBackTests(unittest.TestCase):
    def test_default_back_goes_to_admin_product_hub(self) -> None:
        self.assertIn("nv:adm:product", _callbacks(pg_hub_keyboard(None, features=frozenset())))

    def test_reseller_back_goes_to_reseller_home(self) -> None:
        cbs = _callbacks(
            pg_hub_keyboard(None, features=frozenset(), back_callback="nv:res:home")
        )
        self.assertIn("nv:res:home", cbs)
        self.assertNotIn("nv:adm:product", cbs)


if __name__ == "__main__":
    unittest.main()
