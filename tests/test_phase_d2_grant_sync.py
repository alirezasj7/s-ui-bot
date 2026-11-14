"""Phase D2 — dual grant flows, username equality, no silent conversion."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pg_staff_access import assert_web_matches_pg


_OK = "AaBb12!secret"


class UsernameEqualityTests(unittest.TestCase):
    def test_match_ok(self):
        self.assertIsNone(assert_web_matches_pg("Staff1", "staff1"))

    def test_mismatch_errors(self):
        err = assert_web_matches_pg("other", "staff1")
        self.assertIsNotNone(err)
        self.assertIn("دقیقاً", err)


class GrantWebAccessEqualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_mismatched_username(self):
        from app.services import pg_staff_access as psa

        with patch.object(
            psa, "conflict_message_for_new_grant", new=AsyncMock(return_value=None)
        ):
            row, err = await psa.grant_web_access(
                AsyncMock(),
                pg_username="pgadmin1",
                web_username="webother",
                password=_OK,
            )
        self.assertIsNone(row)
        self.assertIn("دقیقاً", err or "")


class ProvisionNoConversionTests(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_when_staff_exists(self):
        from app.services.resellers import provision_existing_pg_admin

        staff = SimpleNamespace(id=1, pg_username="pgx", web_username="pgx")
        plan = SimpleNamespace(id=1, is_active=True, web_permissions="dashboard", bot_permissions="dashboard")
        session = AsyncMock()
        session.get = AsyncMock(return_value=plan)

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=staff),
            ),
            patch(
                "app.services.web_auth.load_web_admin",
                return_value={"username": "owner"},
            ),
        ):
            profile, hint, err = await provision_existing_pg_admin(
                session,
                pg_username="pgx",
                web_username="pgx",
                password=_OK,
                plan_id=1,
            )
        self.assertIsNone(profile)
        self.assertIsNone(hint)
        self.assertIn("ادمین فرعی", err or "")
        self.assertIn("تبدیل خودکار", err or "")

    async def test_no_revoke_in_source(self):
        src = Path("app/services/resellers.py").read_text(encoding="utf-8")
        # Slice only provision_existing_pg_admin — convert_staff_to_reseller
        # (which follows) intentionally calls revoke_web_access.
        fn = src[
            src.find("async def provision_existing_pg_admin") : src.find(
                "async def convert_staff_to_reseller"
            )
        ]
        self.assertNotIn("revoke_web_access", fn)
        self.assertIn("تبدیل خودکار به نماینده مجاز نیست", fn)


class RouteContractTests(unittest.TestCase):
    def test_legacy_hard_fails(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        legacy = src[
            src.find("async def pg_admins_web_access_legacy") : src.find(
                "async def pg_admins_web_access_staff"
            )
        ]
        self.assertIn("منسوخ", legacy)
        self.assertNotIn("provision_existing_pg_admin", legacy)
        self.assertNotIn("grant_web_access", legacy)

    def test_staff_route_uses_grant(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def pg_admins_web_access_staff") : src.find(
                "async def pg_admins_web_access_reseller"
            )
        ]
        self.assertIn("grant_web_access", fn)
        self.assertIn("update_web_access", fn)
        self.assertNotIn("provision_existing_pg_admin", fn)

    def test_reseller_route_uses_provision(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def pg_admins_web_access_reseller") : src.find(
                "async def pg_admins_web_access_revoke"
            )
        ]
        self.assertIn("provision_existing_pg_admin", fn)
        self.assertNotIn("grant_web_access", fn)

    def test_no_owner_fallback_in_staff_pg(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertIn("get_pg_for_staff", fn)


class StaffPgAsOwnerContractTests(unittest.IsolatedAsyncioTestCase):
    """Behavioral replacement for the old brittle source-string assertion:
    pg_staff must never get ``as_owner=True`` out of ``_staff_pg``, regardless
    of the exact wording of the admin branch (which legitimately changed for
    Hybrid Owner support — admin's ``as_owner`` now reflects the real
    ``pg_is_owner`` flag instead of being hardcoded ``True``).
    """

    async def test_pg_staff_never_gets_as_owner_true(self):
        from app.api.pg_pages import _staff_pg

        with patch(
            "app.services.pasarguard.get_pg_for_staff",
            new=AsyncMock(return_value=MagicMock()),
        ):
            _client, as_owner = await _staff_pg(
                AsyncMock(),
                {
                    "role": "pg_staff",
                    "pg_admin_username": "s1",
                    "pg_staff_id": 9,
                    "pg_is_owner": True,
                },
            )
        self.assertFalse(as_owner)


class ChangeStaffCredentialsEqualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_rename_away_from_pg(self):
        from app.services import pg_staff_access as psa

        row = SimpleNamespace(
            id=1,
            pg_username="samepg",
            web_username="samepg",
            web_password_hash="hash",
        )
        with (
            patch.object(psa, "verify_password_hash", return_value=True),
            patch.object(psa, "_username_taken", new=AsyncMock(return_value=None)),
        ):
            out, err = await psa.change_staff_credentials(
                AsyncMock(),
                row,
                old_username="samepg",
                current_password="old",
                new_username="othername",
                new_password=_OK,
            )
        self.assertIsNone(out)
        self.assertIn("دقیقاً", err or "")


if __name__ == "__main__":
    unittest.main()
