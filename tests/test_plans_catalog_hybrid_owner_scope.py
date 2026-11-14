"""Regression test: a Hybrid Owner's own PasarGuard group/template
restriction must not be silently ignored in the web panel.

``filter_templates_for_staff``, ``filter_groups_for_staff``,
``template_allowed_for_staff`` and ``groups_allowed_for_staff`` used to
short-circuit unconditionally for ``role == "admin"`` regardless of whether
the platform's own ``.env`` PasarGuard account is the real owner or a
*limited* admin (Hybrid Owner setup, ``pg_is_owner=False``). That let a
restricted admin account (e.g. one PasarGuard only grants access to groups 1
and 2) see/select every group and template in the web panel, exactly
contradicting the operator's own PasarGuard configuration. Genuine owners
(``pg_is_owner=True`` or unset, e.g. non-Hybrid single-owner deployments)
must keep their unrestricted behavior unchanged.
"""

from __future__ import annotations

import unittest

from app.services.plans_catalog import (
    filter_groups_for_staff,
    filter_templates_for_staff,
    groups_allowed_for_staff,
    template_allowed_for_staff,
)

GROUPS = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
TEMPLATES = [{"id": 10}, {"id": 20}, {"id": 30}]


class HybridOwnerRestrictedAdminTests(unittest.TestCase):
    def _restricted_admin(self, allowed_group_ids=(1, 2), allowed_template_ids=(10,)):
        return {
            "role": "admin",
            "pg_is_owner": False,
            "pg_access": {
                "allowed_group_ids": list(allowed_group_ids),
                "allowed_template_ids": list(allowed_template_ids),
            },
        }

    def test_restricted_admin_groups_are_filtered(self):
        staff = self._restricted_admin()
        out = filter_groups_for_staff(GROUPS, staff)
        self.assertEqual({g["id"] for g in out}, {1, 2})

    def test_restricted_admin_templates_are_filtered(self):
        staff = self._restricted_admin()
        out = filter_templates_for_staff(TEMPLATES, staff)
        self.assertEqual({t["id"] for t in out}, {10})

    def test_restricted_admin_cannot_use_disallowed_group(self):
        staff = self._restricted_admin()
        self.assertFalse(groups_allowed_for_staff(staff, [3]))
        self.assertFalse(groups_allowed_for_staff(staff, [1, 3]))

    def test_restricted_admin_can_use_allowed_group(self):
        staff = self._restricted_admin()
        self.assertTrue(groups_allowed_for_staff(staff, [1, 2]))

    def test_restricted_admin_cannot_use_disallowed_template(self):
        staff = self._restricted_admin()
        self.assertFalse(template_allowed_for_staff(staff, 20))

    def test_restricted_admin_can_use_allowed_template(self):
        staff = self._restricted_admin()
        self.assertTrue(template_allowed_for_staff(staff, 10))


class GenuineOwnerUnaffectedTests(unittest.TestCase):
    """Existing single-owner (non-Hybrid) behavior must be unchanged."""

    def test_owner_sees_all_groups(self):
        staff = {"role": "admin", "pg_is_owner": True}
        self.assertEqual(filter_groups_for_staff(GROUPS, staff), GROUPS)

    def test_owner_sees_all_templates(self):
        staff = {"role": "admin", "pg_is_owner": True}
        self.assertEqual(filter_templates_for_staff(TEMPLATES, staff), TEMPLATES)

    def test_owner_can_use_any_group(self):
        staff = {"role": "admin", "pg_is_owner": True}
        self.assertTrue(groups_allowed_for_staff(staff, [1, 2, 3, 4]))

    def test_owner_can_use_any_template(self):
        staff = {"role": "admin", "pg_is_owner": True}
        self.assertTrue(template_allowed_for_staff(staff, 999))

    def test_missing_pg_is_owner_key_defaults_to_unrestricted(self):
        """Legacy / non-Hybrid staff dicts (no pg_is_owner key at all) keep
        prior unrestricted behavior — this fix must not break existing
        single-owner deployments."""
        staff = {"role": "admin"}
        self.assertEqual(filter_groups_for_staff(GROUPS, staff), GROUPS)
        self.assertTrue(groups_allowed_for_staff(staff, [1, 2, 3, 4]))


class NonAdminRolesUnaffectedTests(unittest.TestCase):
    def test_reseller_still_uses_own_pg_access(self):
        staff = {
            "role": "reseller",
            "pg_access": {"allowed_group_ids": [2]},
        }
        out = filter_groups_for_staff(GROUPS, staff, trust_client_scope=True)
        self.assertEqual({g["id"] for g in out}, {2})


if __name__ == "__main__":
    unittest.main()
