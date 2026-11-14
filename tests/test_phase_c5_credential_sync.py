"""Phase C5 — pg_staff PasarGuard credential storage and client selection."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pasarguard import PasarGuardError
from app.services.pg_read import (
    PgReadDenied,
    effective_pg_menu_keys,
    staff_has_own_pg_read,
    staff_pg_credentials_ready,
    staff_pg_read_client,
)
from app.services.secret_box import encrypt_secret


class StaffPasswordHelperTests(unittest.TestCase):
    def test_ready_when_encrypted(self):
        from app.services.pg_staff_access import staff_has_stored_pg_password

        enc = encrypt_secret("Secret1!aa")
        row = SimpleNamespace(pg_admin_password_enc=enc)
        self.assertTrue(staff_has_stored_pg_password(row))

    def test_not_ready_when_missing(self):
        from app.services.pg_staff_access import staff_has_stored_pg_password

        self.assertFalse(staff_has_stored_pg_password(None))
        self.assertFalse(
            staff_has_stored_pg_password(SimpleNamespace(pg_admin_password_enc=None))
        )
        self.assertFalse(
            staff_has_stored_pg_password(SimpleNamespace(pg_admin_password_enc=""))
        )


class CredentialsReadyFlagTests(unittest.TestCase):
    def test_pg_staff_flag(self):
        self.assertFalse(
            staff_pg_credentials_ready({"role": "pg_staff", "pg_credentials_ready": False})
        )
        self.assertTrue(
            staff_pg_credentials_ready({"role": "pg_staff", "pg_credentials_ready": True})
        )

    def test_admin_and_reseller_ready(self):
        self.assertFalse(staff_pg_credentials_ready({"role": "admin"}))
        self.assertTrue(
            staff_pg_credentials_ready(
                {
                    "role": "admin",
                    "org_principal_id": 1,
                    "org_depth": 0,
                    "org_parent_id": None,
                    "org_status": "active",
                }
            )
        )
        self.assertTrue(
            staff_pg_credentials_ready({"role": "reseller", "bot_user_id": 1})
        )

    def test_menu_with_credentials_keeps_mapped_keys(self):
        staff = {
            "role": "pg_staff",
            "pg_credentials_ready": True,
            "pg_permissions": ["pg_overview", "pg_users", "pg_hosts"],
        }
        self.assertTrue(staff_has_own_pg_read(staff))
        self.assertEqual(
            effective_pg_menu_keys(staff),
            ["pg_overview", "pg_users", "pg_hosts"],
        )

    def test_menu_without_credentials_overview_only(self):
        staff = {
            "role": "pg_staff",
            "pg_credentials_ready": False,
            "pg_permissions": ["pg_overview", "pg_users", "pg_hosts"],
        }
        self.assertEqual(effective_pg_menu_keys(staff), ["pg_overview"])


class GetPgForStaffTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_encrypted_password(self):
        from app.services.pasarguard import get_pg_for_staff

        row = SimpleNamespace(
            id=1,
            pg_username="staff1",
            is_active=True,
            pg_admin_password_enc=None,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=row)
        with self.assertRaises(PasarGuardError) as ctx:
            await get_pg_for_staff(session, staff_id=1)
        self.assertIn("ذخیره نشده", str(ctx.exception))

    async def test_builds_client_with_decrypted_password(self):
        from app.services.pasarguard import get_pg_for_staff, reset_pg

        reset_pg()
        enc = encrypt_secret("StaffPass1!")
        row = SimpleNamespace(
            id=2,
            pg_username="StaffOne",
            is_active=True,
            pg_admin_password_enc=enc,
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=row)
        fake = MagicMock()
        fake._token = "t"
        fake.ensure_token = AsyncMock()
        with patch(
            "app.services.pasarguard.PasarGuardClient",
            return_value=fake,
        ) as ctor:
            client = await get_pg_for_staff(session, staff_id=2)
        self.assertIs(client, fake)
        ctor.assert_called_once_with(username="StaffOne", password="StaffPass1!")
        fake.ensure_token.assert_awaited_once()
        reset_pg()


class StaffPgReadWriteWithCredentialsTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_uses_get_pg_for_staff(self):
        fake = object()
        session = MagicMock()
        with patch(
            "app.services.pg_read.get_pg_for_staff",
            new=AsyncMock(return_value=fake),
        ) as m:
            client = await staff_pg_read_client(
                session,
                {
                    "role": "pg_staff",
                    "pg_admin_username": "s1",
                    "pg_staff_id": 9,
                    "pg_credentials_ready": True,
                },
            )
        self.assertIs(client, fake)
        m.assert_awaited_once_with(session, pg_username="s1", staff_id=9)

    async def test_read_without_password_denied(self):
        with patch(
            "app.services.pg_read.get_pg_for_staff",
            new=AsyncMock(side_effect=PasarGuardError("رمز ذخیره نشده")),
        ):
            with self.assertRaises(PgReadDenied):
                await staff_pg_read_client(
                    MagicMock(),
                    {"role": "pg_staff", "pg_admin_username": "s1"},
                )

    async def test_write_uses_staff_client_never_owner(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        with (
            patch("app.api.pg_pages.get_pg") as gp,
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(return_value=fake),
            ),
        ):
            client, as_owner = await _staff_pg(
                AsyncMock(),
                {
                    "role": "pg_staff",
                    "pg_admin_username": "s1",
                    "pg_staff_id": 3,
                    "pg_credentials_ready": True,
                },
            )
        self.assertFalse(as_owner)
        self.assertIs(client, fake)
        gp.assert_not_called()

    async def test_write_without_credentials_fail_closed(self):
        from app.api.pg_pages import _staff_pg

        with (
            patch("app.api.pg_pages.get_pg") as gp,
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(side_effect=PasarGuardError("رمز ذخیره نشده")),
            ),
        ):
            with self.assertRaises(PasarGuardError):
                await _staff_pg(
                    AsyncMock(),
                    {"role": "pg_staff", "pg_admin_username": "s1"},
                )
        gp.assert_not_called()

    async def test_assert_owned_user_uses_staff_client(self):
        from app.api.pg_pages import _assert_owned_user

        staff_pg = AsyncMock()
        staff_pg.get_user_by_id = AsyncMock(
            return_value={"id": 5, "username": "u", "admin": {"username": "s1"}}
        )
        owner = AsyncMock()
        owner.get_user_by_id = AsyncMock(return_value={"id": 5})
        with (
            patch("app.api.pg_pages.get_pg", return_value=owner),
            patch(
                "app.services.pasarguard.get_pg_for_staff",
                new=AsyncMock(return_value=staff_pg),
            ),
        ):
            info = await _assert_owned_user(
                {
                    "role": "pg_staff",
                    "pg_admin_username": "s1",
                    "pg_staff_id": 1,
                },
                5,
                session=AsyncMock(),
            )
        self.assertEqual(info["username"], "u")
        staff_pg.get_user_by_id.assert_awaited_once_with(5)
        owner.get_user_by_id.assert_not_awaited()


class GrantStoresEncryptedPasswordTests(unittest.IsolatedAsyncioTestCase):
    async def test_grant_encrypts_and_syncs_pg(self):
        from app.services import pg_staff_access as psa

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        pg = MagicMock()
        pg.modify_admin = AsyncMock()
        created: list = []
        session.add.side_effect = lambda row: created.append(row)

        with (
            patch.object(psa, "conflict_message_for_new_grant", new=AsyncMock(return_value=None)),
            patch.object(psa, "_username_taken", new=AsyncMock(return_value=None)),
            patch.object(psa, "resolve_pg_role_id_for_admin", new=AsyncMock(return_value=42)),
            patch.object(psa, "hash_password", return_value="hashed"),
            patch("app.services.pasarguard.get_pg", return_value=pg),
            patch("app.services.pasarguard.reset_pg"),
            patch(
                "app.services.secret_box.encrypt_secret",
                return_value="enc-token",
            ),
        ):
            row, err = await psa.grant_web_access(
                session,
                pg_username="PgStaff1",
                web_username="pgstaff1",
                password="AaBb12!secret",
            )
        self.assertIsNone(err)
        self.assertIsNotNone(row)
        self.assertEqual(row.pg_admin_password_enc, "enc-token")
        self.assertEqual(row.pg_role_id, 42)
        pg.modify_admin.assert_awaited_once_with("pgstaff1", {"password": "AaBb12!secret"})
        self.assertTrue(created)
        self.assertEqual(row.pg_username, "pgstaff1")


class SourceGuardsC5(unittest.TestCase):
    def test_model_has_credential_columns(self):
        from app.db.models import PgStaffAccess

        cols = PgStaffAccess.__table__.c.keys()
        self.assertIn("pg_admin_password_enc", cols)
        self.assertIn("pg_role_id", cols)

    def test_alembic_migration_exists(self):
        path = Path("alembic/versions/0002_pg_staff_credentials.py")
        self.assertTrue(path.is_file())
        src = path.read_text(encoding="utf-8")
        self.assertIn("pg_admin_password_enc", src)
        self.assertIn("0001_baseline", src)

    def test_staff_pg_uses_get_pg_for_staff(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertIn("get_pg_for_staff", fn)
        self.assertIn('staff.get("role") == "pg_staff"', fn)
        self.assertIn("), False", fn)


class StaffPgAsOwnerContractTests(unittest.IsolatedAsyncioTestCase):
    """Behavioral replacement for the old brittle ``fn.count("return get_pg(), "
    "True") == 1`` source-string assertions (rewritten per the security audit
    testing hardening pass): what actually matters is that ``pg_staff`` can
    never get ``as_owner=True`` — not the exact literal text of the admin
    branch, which legitimately changed when Hybrid Owner support landed
    (admin's ``as_owner`` now reflects the real ``pg_is_owner`` flag instead
    of being hardcoded).
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
                    # Even if something upstream mistakenly sets this, pg_staff
                    # must never inherit owner privileges through _staff_pg.
                    "pg_is_owner": True,
                },
            )
        self.assertFalse(as_owner)

    async def test_full_owner_admin_gets_as_owner_true(self):
        from app.api.pg_pages import _staff_pg

        with patch("app.api.pg_pages.get_pg", return_value=MagicMock()):
            _client, as_owner = await _staff_pg(
                AsyncMock(),
                {
                    "role": "admin",
                    "web_owner": True,
                    "pg_is_owner": True,
                    "org_principal_id": 1,
                    "org_depth": 0,
                    "org_parent_id": None,
                    "org_status": "active",
                },
            )
        self.assertTrue(as_owner)

    async def test_hybrid_limited_admin_does_not_get_as_owner_true(self):
        from app.api.pg_pages import _staff_pg

        with patch("app.api.pg_pages.get_pg", return_value=MagicMock()):
            _client, as_owner = await _staff_pg(
                AsyncMock(),
                {
                    "role": "admin",
                    "web_owner": True,
                    "pg_is_owner": False,
                    "org_principal_id": 1,
                    "org_depth": 0,
                    "org_parent_id": None,
                    "org_status": "active",
                },
            )
        self.assertFalse(as_owner)


if __name__ == "__main__":
    unittest.main()
