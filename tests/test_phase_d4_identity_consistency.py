"""Phase D4 — Web/Bot identity consistency: role boundaries, no Bot PG, no Owner fallback."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.authz import (
    PrincipalKind,
    authz_from_staff,
    can_shop,
    principal_kind_from_role,
    shop_feature_allowed,
    shop_menu_keys,
)
from app.services.platform_identity import (
    deliverable_telegram_id,
    feature_perm_keys,
    identity_help_fa,
    is_bot_platform_admin,
    is_synthetic_telegram_id,
    is_web_platform_admin,
)
from app.services.resellers import FEATURE_PERMS, has_bot_perm, has_perm


# Repo root — avoid Path("…") relative to CWD (Phase B CLI chdirs during tests).
_ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class PlatformIdentityHelperTests(unittest.TestCase):
    def test_web_platform_admin(self):
        self.assertTrue(is_web_platform_admin({"role": "admin"}))
        self.assertFalse(is_web_platform_admin({"role": "reseller"}))
        self.assertFalse(is_web_platform_admin({"role": "pg_staff"}))
        self.assertFalse(is_web_platform_admin(None))

    def test_bot_platform_admin_role_and_ids(self):
        admin = SimpleNamespace(role="admin", telegram_id=1)
        self.assertTrue(is_bot_platform_admin(admin, admin_ids=set()))
        listed = SimpleNamespace(role="user", telegram_id=42)
        self.assertTrue(is_bot_platform_admin(listed, admin_ids={42}))
        other = SimpleNamespace(role="reseller", telegram_id=7)
        self.assertFalse(is_bot_platform_admin(other, admin_ids={42}))
        # Synthetic id never counts as bot platform admin via ADMIN_IDS alone
        synth = SimpleNamespace(role="user", telegram_id=-99)
        self.assertFalse(is_bot_platform_admin(synth, admin_ids={-99}))

    def test_bot_auth_delegates(self):
        from app.bot.auth import is_platform_admin

        with patch(
            "app.services.platform_identity.is_bot_platform_admin",
            return_value=True,
        ) as m:
            user = SimpleNamespace(role="admin", telegram_id=1)
            self.assertTrue(is_platform_admin(user))
            m.assert_called()

    def test_shop_scope_delegates(self):
        from app.services.shop_scope import is_platform_admin as web_admin

        # Phase 1G: shop platform privilege requires explicit Owner Principal.
        self.assertFalse(web_admin({"role": "admin"}))
        self.assertTrue(
            web_admin(
                {
                    "role": "admin",
                    "org_principal_id": 1,
                    "org_depth": 0,
                    "org_parent_id": None,
                    "org_status": "active",
                }
            )
        )
        self.assertFalse(web_admin({"role": "pg_staff"}))

    def test_synthetic_telegram_ids(self):
        self.assertTrue(is_synthetic_telegram_id(None))
        self.assertTrue(is_synthetic_telegram_id(0))
        self.assertTrue(is_synthetic_telegram_id(-1))
        self.assertFalse(is_synthetic_telegram_id(12345))
        self.assertIsNone(deliverable_telegram_id(-5))
        self.assertEqual(deliverable_telegram_id(9), 9)

    def test_identity_help_covers_roles(self):
        for role in ("admin", "pg_staff", "reseller"):
            help_ = identity_help_fa(role)
            self.assertTrue(help_["title"])
            self.assertGreaterEqual(len(help_["lines"]), 1)


class RoleBoundaryTests(unittest.TestCase):
    def test_pg_staff_no_shop_web(self):
        staff = {"role": "pg_staff", "permissions": [], "pg_permissions": ["pg_overview"]}
        self.assertEqual(shop_menu_keys(staff=staff), frozenset())
        for key, _ in FEATURE_PERMS:
            self.assertFalse(can_shop(authz_from_staff(staff), key), key)
            self.assertFalse(shop_feature_allowed(key=key, staff=staff), key)

    def test_reseller_shop_web_bot_parity(self):
        profile = SimpleNamespace(
            is_active=True,
            web_permissions="dashboard,orders",
            bot_permissions="stats",  # stale mirror — ignored for decisions
        )
        for key, _ in FEATURE_PERMS:
            bot = has_bot_perm(profile, key)
            via = shop_feature_allowed(key=key, profile=profile)
            self.assertEqual(bot, via, key)

        # Empty web ACL denies even if bot_permissions mirror lists a key
        denied = SimpleNamespace(
            is_active=True,
            web_permissions="",
            bot_permissions="payments,stats",
        )
        self.assertFalse(has_bot_perm(denied, "payments"))
        self.assertFalse(has_perm(denied, "payments"))

        staff = {
            "role": "reseller",
            "permissions": list(shop_menu_keys(profile=profile)),
        }
        for key in staff["permissions"]:
            self.assertTrue(can_shop(authz_from_staff(staff), key), key)

    def test_admin_web_and_bot_bypass_shop(self):
        profile = SimpleNamespace(is_active=True, web_permissions="")
        self.assertTrue(has_perm(profile, "payments", role="admin"))
        from app.bot.auth import can_shop_feature

        admin = SimpleNamespace(role="admin", telegram_id=1)
        self.assertTrue(can_shop_feature("payments", profile=profile, db_user=admin))

    def test_owner_kind_unused_for_session_admin(self):
        # Q1 A: session admin maps to PLATFORM_ADMIN, not OWNER
        self.assertEqual(principal_kind_from_role("admin"), PrincipalKind.PLATFORM_ADMIN)
        self.assertEqual(principal_kind_from_role("pg_staff"), PrincipalKind.PG_STAFF)
        self.assertEqual(principal_kind_from_role("reseller"), PrincipalKind.RESELLER)

    def test_feature_perm_keys_stable(self):
        keys = feature_perm_keys()
        self.assertIn("dashboard", keys)
        self.assertIn("shop_settings", keys)
        self.assertEqual(keys, frozenset(k for k, _ in FEATURE_PERMS))


class NoBotPgContracts(unittest.TestCase):
    def test_admin_pg_users_uses_owner_client_only(self):
        src = _read("app/bot/handlers/admin_pg_users.py")
        self.assertIn("get_pg()", src)
        self.assertNotIn("get_pg_for_staff", src)
        self.assertNotIn("get_pg_for_reseller", src)
        self.assertIn("is_platform_admin", src)

    def test_admin_handler_pg_uses_owner_client_only(self):
        src = _read("app/bot/handlers/admin.py")
        # Platform admin PG tools only
        self.assertIn("get_pg()", src)
        self.assertNotIn("get_pg_for_staff", src)
        self.assertNotIn("get_pg_for_reseller", src)

    def test_reseller_bot_handlers_no_pg_clients(self):
        for rel in (
            "app/bot/handlers/reseller.py",
            "app/bot/handlers/reseller_plans.py",
            "app/bot/handlers/reseller_settings.py",
        ):
            src = _read(rel)
            self.assertNotIn("get_pg_for_staff", src, rel)
            # Owner env client is forbidden on shop-bot handlers.
            # Own-shop ``get_pg_for_reseller`` is allowed (Web/Bot PG parity).
            self.assertNotIn("get_pg()", src, rel)


class NoOwnerFallbackContracts(unittest.TestCase):
    def test_staff_pg_no_owner_fallback_for_staff(self):
        src = _read("app/api/pg_pages.py")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertIn("get_pg_for_staff", fn)
        self.assertIn("get_pg_for_reseller", fn)

    def test_pg_read_staff_fail_closed(self):
        src = _read("app/services/pg_read.py")
        self.assertIn("get_pg_for_staff", src)
        self.assertIn("PgReadDenied", src)
        # Must not quietly fall back to get_pg for pg_staff
        self.assertNotIn('role == "pg_staff"\n        return get_pg()', src)


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


class UiAndDocsContracts(unittest.TestCase):
    def test_security_template_identity_help(self):
        tpl = _read("app/web/templates/security.html")
        self.assertIn("identity_help", tpl)
        self.assertIn("identity-help", tpl)

    def test_security_route_passes_help(self):
        src = _read("app/api/security.py")
        self.assertIn("identity_help_fa", src)
        self.assertIn("identity_help", src)

    def test_matrix_doc_exists(self):
        text = _read("docs/PHASE_D4_IDENTITY_MATRIX.md")
        self.assertIn("pg_staff", text)
        self.assertIn("web-only", text)
        self.assertIn("ADMIN_IDS", text)

    def test_bot_permissions_mirror_documented(self):
        src = _read("app/services/resellers.py")
        fn = src[src.find("def has_bot_perm") : src.find("def setup_is_complete")]
        self.assertIn("mirrored", fn.lower() + fn)
        self.assertIn("never read", fn.lower() + fn)


if __name__ == "__main__":
    unittest.main()
