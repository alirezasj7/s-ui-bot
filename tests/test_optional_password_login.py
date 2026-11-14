"""Optional password on edit + login session clear after PG→reseller conversion."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.resellers import make_reseller, setup_is_complete


class OptionalPasswordUiTests(unittest.TestCase):
    def test_pg_admins_password_not_required_on_upgrade(self):
        src = Path("app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn('{% if src == \'none\' %}required{% endif %}', src)
        self.assertIn("خالی = حفظ رمز فعلی", src)

    def test_reseller_edit_has_optional_password(self):
        src = Path("app/web/templates/_reseller_edit_body.html").read_text(encoding="utf-8")
        self.assertIn('name="web_password"', src)
        self.assertIn("خالی = حفظ رمز فعلی", src)
        # Must not force required on edit
        block = src.split('name="web_password"', 1)[1].split("</label>", 1)[0]
        self.assertNotIn("required", block)

    def test_reseller_edit_save_handles_password(self):
        src = Path("app/api/reseller_pages.py").read_text(encoding="utf-8")
        self.assertIn('form.get("web_password")', src)
        self.assertIn("validate_password_strength", src)

    def test_unauth_clears_session_cookie(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn('resp.delete_cookie("session", path="/")', src)
        self.assertIn("login.html", src)
        # Login with err must not blind-redirect
        self.assertIn("if not err:", src)


class ProvisionPasswordKeepTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_password_reuses_staff_hash(self):
        """Empty password reuses existing reseller hash (pg_staff auto-convert is blocked)."""
        from app.services.resellers import provision_existing_pg_admin

        plan = SimpleNamespace(
            id=1,
            is_active=True,
            web_permissions="dashboard,plans",
            bot_permissions="dashboard,plans",
            billing_mode="fixed",
        )
        existing = SimpleNamespace(
            id=3,
            web_username="pgadmin",
            web_password_hash="kept-hash",
            pg_admin_username="pgadmin",
            pg_admin_password_enc="enc-secret",
            is_active=True,
            bot_token=None,
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=plan)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        call_n = {"n": 0}

        async def _exec(stmt):
            call_n["n"] += 1
            result = MagicMock()
            # 1st execute: linked resellers (.scalars().all)
            result.scalars.return_value.all.return_value = [existing]
            # later: username uniqueness — same reseller ok; staff clash none
            result.scalar_one_or_none.return_value = (
                existing if call_n["n"] == 2 else None
            )
            return result

        session.execute = AsyncMock(side_effect=_exec)

        captured = {}

        async def _fake_make(session, user, **kwargs):
            captured.update(kwargs)
            existing.web_password_hash = kwargs.get("web_password_hash")
            return existing

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.conflict_message_for_reseller_link",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.resolve_pg_role_id_for_admin",
                new=AsyncMock(return_value=3),
            ),
            patch(
                "app.services.web_auth.load_web_admin",
                return_value={"username": "admin"},
            ),
            patch(
                "app.services.secret_box.decrypt_secret",
                return_value="plain-pg-pass",
            ),
            patch(
                "app.services.resellers.get_or_create_pg_linked_bot_user",
                new=AsyncMock(return_value=SimpleNamespace(id=55, role="user")),
            ),
            patch("app.services.resellers.make_reseller", new=_fake_make),
            # This test is about the password; the subscription step is not under test here.
            patch("app.services.pg_admin_subscription.start_or_refresh_subscription", new=AsyncMock()),
        ):
            profile, _hint, err = await provision_existing_pg_admin(
                session,
                pg_username="pgadmin",
                web_username="pgadmin",
                password="",
                plan_id=1,
            )
        self.assertIsNone(err)
        self.assertIsNotNone(profile)
        self.assertEqual(captured.get("web_password_hash"), "kept-hash")

    async def test_pg_staff_cannot_auto_convert(self):
        from app.services.resellers import provision_existing_pg_admin

        plan = SimpleNamespace(
            id=1,
            is_active=True,
            web_permissions="dashboard,plans",
            bot_permissions="dashboard,plans",
        )
        staff = SimpleNamespace(
            web_password_hash="kept-hash",
            web_username="staff1",
            pg_username="pgadmin",
            id=9,
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=plan)

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=staff),
            ),
            patch(
                "app.services.web_auth.load_web_admin",
                return_value={"username": "admin"},
            ),
        ):
            profile, _hint, err = await provision_existing_pg_admin(
                session,
                pg_username="pgadmin",
                web_username="pgadmin",
                password="",
                plan_id=1,
            )
        self.assertIsNone(profile)
        self.assertIsNotNone(err)
        self.assertIn("تبدیل خودکار به نماینده مجاز نیست", err)

    async def test_empty_password_without_prior_hash_fails(self):
        from app.services.resellers import provision_existing_pg_admin

        plan = SimpleNamespace(
            id=1,
            is_active=True,
            web_permissions="dashboard",
            bot_permissions="dashboard",
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=plan)

        async def _exec(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=_exec)

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.conflict_message_for_reseller_link",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.web_auth.load_web_admin",
                return_value={"username": "admin"},
            ),
        ):
            profile, _hint, err = await provision_existing_pg_admin(
                session,
                pg_username="newadmin",
                web_username="newadmin",
                password="",
                plan_id=1,
            )
        self.assertIsNone(profile)
        self.assertEqual(err, "رمز عبور الزامی است")

    async def test_web_username_must_match_pg(self):
        from app.services.resellers import provision_existing_pg_admin

        plan = SimpleNamespace(
            id=1,
            is_active=True,
            web_permissions="dashboard",
            bot_permissions="dashboard",
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=plan)

        async def _exec(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=_exec)

        with (
            patch(
                "app.services.pg_staff_access.access_by_pg_username",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.pg_staff_access.conflict_message_for_reseller_link",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.web_auth.load_web_admin",
                return_value={"username": "admin"},
            ),
        ):
            profile, _hint, err = await provision_existing_pg_admin(
                session,
                pg_username="newadmin",
                web_username="newweb",
                password="ValidPass1!",
                plan_id=1,
            )
        self.assertIsNone(profile)
        self.assertIn("نام کاربری وب باید دقیقاً همان نام ادمین پاسارگارد", err)

class SetupCompleteKeepHashTests(unittest.TestCase):
    def test_setup_complete_with_creds(self):
        p = SimpleNamespace(
            is_active=True,
            setup_completed_at="x",
            web_username="u",
            web_password_hash="h",
        )
        self.assertTrue(setup_is_complete(p))

    def test_make_reseller_setup_uses_existing_hash(self):
        src = inspect.getsource(make_reseller)
        self.assertIn("web_password_hash or profile.web_password_hash", src)


class UpdateWebAccessOptionalPasswordTests(unittest.TestCase):
    def test_empty_password_kept_on_update(self):
        src = Path("app/services/pg_staff_access.py").read_text(encoding="utf-8")
        # update_web_access keeps hash; grant_web_access still requires password
        update_fn = src.split("async def update_web_access", 1)[1].split(
            "async def upsert_web_access", 1
        )[0]
        self.assertIn("Keep existing password on edit", update_fn)
        self.assertNotIn('return None, "رمز عبور الزامی است"', update_fn)
        grant_fn = src.split("async def grant_web_access", 1)[1].split(
            "async def update_web_access", 1
        )[0]
        self.assertIn('return None, "رمز عبور الزامی است"', grant_fn)


if __name__ == "__main__":
    unittest.main()
