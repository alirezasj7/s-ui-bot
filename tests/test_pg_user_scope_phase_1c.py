"""Phase 1C — PG user object scope (H1 + M6)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import pg_pages
from app.services.pg_user_scope import (
    filter_pg_users_for_staff,
    pg_user_in_staff_scope,
    pg_user_owner_username,
)


def _user(uid: int, owner: str | None) -> dict:
    if owner is None:
        return {"id": uid, "username": f"u{uid}"}
    return {"id": uid, "username": f"u{uid}", "admin": {"username": owner}}


class PgUserScopePureTests(unittest.TestCase):
    def test_a_sees_own_users(self) -> None:
        staff = {"pg_admin_username": "admin_a", "pg_is_owner": False}
        users = [_user(1, "admin_a"), _user(2, "admin_b")]
        filtered = filter_pg_users_for_staff(users, staff)
        self.assertEqual([u["id"] for u in filtered], [1])
        self.assertTrue(pg_user_in_staff_scope(_user(1, "admin_a"), staff))

    def test_a_cannot_see_b(self) -> None:
        staff_a = {"pg_admin_username": "admin_a", "pg_is_owner": False}
        self.assertFalse(pg_user_in_staff_scope(_user(2, "admin_b"), staff_a))

    def test_missing_pg_username_empty_list(self) -> None:
        staff = {"role": "admin", "pg_is_owner": False}  # no pg_admin_username
        users = [_user(1, "admin_a"), _user(2, "admin_b")]
        self.assertEqual(filter_pg_users_for_staff(users, staff), [])

    def test_unknown_ownership_deny(self) -> None:
        staff = {"pg_admin_username": "admin_a", "pg_is_owner": False}
        self.assertFalse(pg_user_in_staff_scope(_user(9, None), staff))
        self.assertEqual(pg_user_owner_username(_user(9, None)), "")

    def test_full_pg_owner_sees_all(self) -> None:
        staff = {"pg_is_owner": True, "pg_admin_username": "root"}
        users = [_user(1, "admin_a"), _user(2, "admin_b")]
        self.assertEqual(len(filter_pg_users_for_staff(users, staff)), 2)

    def test_unenriched_owner_admin_compatible(self) -> None:
        """Legacy Owner session (role=admin, unset pg_is_owner) keeps global list."""
        staff = {"role": "admin"}  # no pg_is_owner, no pg_admin_username
        users = [_user(1, "admin_a"), _user(2, "admin_b")]
        self.assertEqual(len(filter_pg_users_for_staff(users, staff)), 2)

    def test_role_names_irrelevant(self) -> None:
        # Same ownership outcome regardless of session role label
        for role in ("admin", "reseller", "pg_staff", "Operator", "whatever"):
            staff = {
                "role": role,
                "pg_admin_username": "admin_a",
                "pg_is_owner": False,
            }
            self.assertTrue(pg_user_in_staff_scope(_user(1, "admin_a"), staff))
            self.assertFalse(pg_user_in_staff_scope(_user(2, "admin_b"), staff))

    def test_same_pg_role_string_isolated_by_username(self) -> None:
        """Arbitrary PasarGuard role *names* do not merge scopes — username does."""
        a = {"pg_admin_username": "alice", "pg_role_name": "RoleX", "pg_is_owner": False}
        b = {"pg_admin_username": "bob", "pg_role_name": "RoleX", "pg_is_owner": False}
        ua = _user(1, "alice")
        ub = _user(2, "bob")
        self.assertTrue(pg_user_in_staff_scope(ua, a))
        self.assertFalse(pg_user_in_staff_scope(ub, a))
        self.assertTrue(pg_user_in_staff_scope(ub, b))
        self.assertFalse(pg_user_in_staff_scope(ua, b))


class AssertOwnedUserTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_a_gets_own(self) -> None:
        staff = {
            "role": "reseller",
            "bot_user_id": 10,
            "pg_admin_username": "admin_a",
            "pg_is_owner": False,
        }
        own = _user(1, "admin_a")
        pg = MagicMock()
        pg.get_user_by_id = AsyncMock(return_value=own)
        with patch("app.api.pg_pages.get_pg_for_reseller", new=AsyncMock(return_value=pg)):
            with patch("app.api.pg_pages.shop_owner_id", return_value=10):
                got = await pg_pages._assert_owned_user(staff, 1, session=MagicMock())
        self.assertEqual(got, own)

    async def test_scoped_a_denied_b_by_id(self) -> None:
        staff = {
            "role": "reseller",
            "bot_user_id": 10,
            "pg_admin_username": "admin_a",
            "pg_is_owner": False,
        }
        foreign = _user(99, "admin_b")
        pg = MagicMock()
        pg.get_user_by_id = AsyncMock(return_value=foreign)
        with patch("app.api.pg_pages.get_pg_for_reseller", new=AsyncMock(return_value=pg)):
            with patch("app.api.pg_pages.shop_owner_id", return_value=10):
                got = await pg_pages._assert_owned_user(staff, 99, session=MagicMock())
        self.assertIsNone(got)

    async def test_id_only_change_denied_for_hybrid_admin(self) -> None:
        staff = {
            "role": "admin",
            "pg_admin_username": "lim",
            "pg_is_owner": False,
        }
        foreign = _user(5, "other")
        with patch("app.api.pg_pages.get_pg") as gpg:
            gpg.return_value.get_user_by_id = AsyncMock(return_value=foreign)
            got = await pg_pages._assert_owned_user(staff, 5, session=None)
        self.assertIsNone(got)

    async def test_missing_username_deny_mutate(self) -> None:
        staff = {"role": "admin", "pg_is_owner": False}
        with patch("app.api.pg_pages.get_pg") as gpg:
            gpg.return_value.get_user_by_id = AsyncMock(
                return_value=_user(1, "anyone")
            )
            got = await pg_pages._assert_owned_user(staff, 1, session=None)
        self.assertIsNone(got)
        gpg.return_value.get_user_by_id.assert_not_called()

    async def test_unknown_ownership_deny(self) -> None:
        staff = {
            "role": "reseller",
            "bot_user_id": 10,
            "pg_admin_username": "admin_a",
            "pg_is_owner": False,
        }
        opaque = _user(3, None)
        pg = MagicMock()
        pg.get_user_by_id = AsyncMock(return_value=opaque)
        with patch("app.api.pg_pages.get_pg_for_reseller", new=AsyncMock(return_value=pg)):
            with patch("app.api.pg_pages.shop_owner_id", return_value=10):
                got = await pg_pages._assert_owned_user(staff, 3, session=MagicMock())
        self.assertIsNone(got)

    async def test_full_owner_compatible(self) -> None:
        staff = {"role": "admin", "pg_is_owner": True, "pg_admin_username": "root"}
        any_user = _user(7, "someone")
        with patch("app.api.pg_pages.get_pg") as gpg:
            gpg.return_value.get_user_by_id = AsyncMock(return_value=any_user)
            got = await pg_pages._assert_owned_user(staff, 7, session=None)
        self.assertEqual(got, any_user)


if __name__ == "__main__":
    unittest.main()
