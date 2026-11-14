"""PG user object-level scope (Phase 1C).

Ownership uses PasarGuard user owner fields + staff ``pg_admin_username`` /
``pg_is_owner`` — never session role names (admin/reseller/operator).

Missing username for a non-owner principal → empty/deny (never global list).
Unknown ownership on a user object → deny.
"""

from __future__ import annotations

from typing import Any, Mapping


def staff_pg_username(staff: Mapping[str, Any] | None) -> str:
    if not staff:
        return ""
    return str(staff.get("pg_admin_username") or "").strip().lower()


def is_full_pg_owner(staff: Mapping[str, Any] | None) -> bool:
    """Whether this principal has global PG user scope (not username-scoped).

    Uses the PasarGuard owner capability flag — never PG/session role *names*
    for matching a user object to a principal.

    - ``pg_is_owner is True`` → global (true Owner / sudo).
    - ``pg_is_owner is False`` → scoped (Hybrid limited); missing username → deny.
    - unset: preserve legacy unenriched platform Owner (``role=admin`` only);
      reseller / pg_staff / Level-1 principal remain scoped.
    """
    if not staff:
        return False
    if staff.get("role") == "principal":
        # Phase 2C: Level-1 never has global PG user scope.
        return False
    flag = staff.get("pg_is_owner")
    if flag is False:
        return False
    if flag is True:
        return True
    # Unset — Owner-compatible default for platform admin sessions only.
    return staff.get("role") == "admin"


def pg_user_owner_username(user: Mapping[str, Any] | None) -> str:
    """Extract owning PG admin username from a PasarGuard user payload."""
    if not isinstance(user, Mapping):
        return ""
    admin = user.get("admin") or user.get("owner_username") or ""
    if isinstance(admin, Mapping):
        admin = admin.get("username") or ""
    return str(admin or "").strip().lower()


def pg_user_in_staff_scope(
    user: Mapping[str, Any] | None,
    staff: Mapping[str, Any] | None,
) -> bool:
    """Whether a loaded PG user belongs to this staff's PG scope.

    Fail closed when ownership cannot be determined for non-owner staff.
    """
    if not isinstance(user, Mapping) or not staff:
        return False
    if is_full_pg_owner(staff):
        return True
    mine = staff_pg_username(staff)
    if not mine:
        return False
    owned = pg_user_owner_username(user)
    if not owned:
        return False
    return owned == mine


def filter_pg_users_for_staff(
    users: list | None,
    staff: Mapping[str, Any] | None,
) -> list[dict]:
    """List filter. Non-owner without pg_username → [] (never global)."""
    if not users:
        return []
    if is_full_pg_owner(staff):
        return [u for u in users if isinstance(u, dict)]
    if not staff_pg_username(staff):
        return []
    return [u for u in users if isinstance(u, dict) and pg_user_in_staff_scope(u, staff)]
