"""Phase 2C / 3D — PasarGuard capability → Web authorization for Principals.

Level-1 and Level-2 use the **same** capability engine:

``map_pg_role_*`` / ``can_pg_*`` / ``authorize()`` / ``staff_pg_action``.

Never keys authority off role *names*. Capabilities come from the Principal's
own PG identity. Scope comes from OrgPrincipal hierarchy. Local safety is
depth-based (Owner-only surfaces never granted to depth 1 or 2).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.authz import (
    AuthDecision,
    authz_from_staff,
    authorize,
    can_pg_action,
    can_pg_page,
    can_pg_user_action,
    has_active_org_principal,
)
from app.services.pg_access import (
    PG_OWNER_ONLY_FEATURES,
    enrich_staff_pg_from_role,
    map_pg_role_actions,
    map_pg_role_to_features,
    map_pg_role_writes,
    role_access_limits,
    role_user_actions,
)
from app.services.principal_web_identity import ROLE_PRINCIPAL


# Application-local Owner-only / platform-secret surfaces (not granted by PG role names).
LEVEL1_BLOCKED_PG_PAGES = frozenset(PG_OWNER_ONLY_FEATURES) | frozenset(
    {
        "pg_admins",
        "backup",
        "ssl",
        "security",
        "updates",
    }
)


def is_level1_principal_staff(staff: Mapping[str, Any] | None) -> bool:
    """True for depth-1 or depth-2 Principal web staff (local-safety clamp).

    Level-2 reuses the same Owner-page / admin-mutation clamps as Level-1.
    """
    if not staff:
        return False
    if (staff.get("role") or "") == ROLE_PRINCIPAL:
        return True
    try:
        depth = int(staff.get("org_depth")) if staff.get("org_depth") is not None else None
    except (TypeError, ValueError):
        depth = None
    return depth in (1, 2) and not bool(staff.get("web_owner"))


def apply_level1_pg_local_safety(
    staff: Mapping[str, Any],
    role: dict | None = None,
) -> dict[str, Any]:
    """Clamp PG capability matrices for depth-1 **and** depth-2 Principals.

    Same function for L1 and L2 — no second permission matrix.

    - Never ``pg_is_owner``
    - Never Owner-only pages (``pg_admins``, backup, …)
    - If PG role flag ``is_owner`` is set, strip it and remap from raw permissions
      only (missing permissions → empty / fail closed)
    """
    out = dict(staff)
    out["pg_is_owner"] = False
    out["web_owner"] = False

    working_role = role
    if working_role is None and isinstance(out.get("pg_role"), dict):
        working_role = out.get("pg_role")  # type: ignore[assignment]

    if isinstance(working_role, dict) and working_role.get("is_owner"):
        raw = dict(working_role)
        raw["is_owner"] = False
        perms = raw.get("permissions")
        if not isinstance(perms, dict) or not perms:
            # Owner-equivalent role with no granular matrix → fail closed for Level-1
            out["pg_permissions"] = []
            out["pg_actions"] = map_pg_role_actions(None)
            out["pg_user_actions"] = role_user_actions(None)
            out["pg_writes"] = map_pg_role_writes(None)
            out["pg_access"] = role_access_limits(None)
            out["pg_capabilities_ok"] = False
            return out
        features = map_pg_role_to_features(raw)
        out = enrich_staff_pg_from_role(out, features, raw)
        out["pg_is_owner"] = False

    features = [
        f
        for f in (out.get("pg_permissions") or [])
        if f not in LEVEL1_BLOCKED_PG_PAGES and f not in PG_OWNER_ONLY_FEATURES
    ]
    out["pg_permissions"] = features
    return out


# L1 and L2 share this clamp — no second permission matrix.
apply_principal_pg_local_safety = apply_level1_pg_local_safety


def principal_pg_authz_ready(staff: Mapping[str, Any] | None) -> bool:
    """Fail-closed PG identity/capability gate for Principal web staff.

    Missing username, explicit ``pg_capabilities_ok=False``, or L2 without
    stored credentials → not ready. Does not consult role *names*.
    """
    if not staff or not is_level1_principal_staff(staff):
        return True
    if staff.get("pg_capabilities_ok") is False:
        return False
    try:
        depth = int(staff.get("org_depth")) if staff.get("org_depth") is not None else None
    except (TypeError, ValueError):
        depth = None
    if depth == 2:
        if not str(staff.get("pg_admin_username") or "").strip():
            return False
        if staff.get("pg_credentials_ready") is False:
            return False
    return True


def local_safety_allows_pg_page(staff: Mapping[str, Any] | None, page_key: str) -> bool:
    if not staff:
        return False
    key = (page_key or "").strip()
    if not key:
        return False
    if is_level1_principal_staff(staff) and key in LEVEL1_BLOCKED_PG_PAGES:
        return False
    return True


def local_safety_allows_pg_action(
    staff: Mapping[str, Any] | None,
    resource: str,
    action: str,
) -> bool:
    """Block Owner-grade mutations for L1/L2 even if PG matrix is wrong."""
    if not staff:
        return False
    if not is_level1_principal_staff(staff):
        return True
    res = (resource or "").strip().lower()
    act = (action or "").strip().lower()
    # Admin / role / platform / hierarchy management — never for depth 1 or 2
    if res in {
        "admins",
        "admin",
        "admin_roles",
        "roles",
        "system",
        "cores",
        "api_keys",
        "principals",
        "org_principals",
    }:
        return False
    if res == "users" and act in {"sudo", "transfer_owner"}:
        return False
    return True


def authorize_pg_page(staff: Mapping[str, Any] | None, page_key: str) -> AuthDecision:
    """Page visibility/access: AUTH ∧ PRINCIPAL ∧ PG page ∧ local safety.

    Scope for page open is the actor's own principal (self-in-scope).
    """
    if not staff:
        return AuthDecision(False, "unauthenticated")
    ctx = authz_from_staff(staff)
    if not has_active_org_principal(ctx):
        return AuthDecision(False, "inactive_or_missing_principal")
    if not principal_pg_authz_ready(staff):
        return AuthDecision(False, "pg_capabilities_unavailable")
    if not local_safety_allows_pg_page(staff, page_key):
        return AuthDecision(False, "local_safety_denied")
    pg_ok = can_pg_page(ctx, page_key)
    return authorize(
        authenticated=True,
        ctx=ctx,
        resource_principal_id=ctx.principal_id,
        pg_permission_ok=pg_ok,
        local_safety_ok=True,
    )


def authorize_pg_action(
    staff: Mapping[str, Any] | None,
    resource: str,
    action: str,
    *,
    resource_principal_id: int | None = None,
) -> AuthDecision:
    """Mutation/action gate: PG action ∧ scope ∧ local safety."""
    if not staff:
        return AuthDecision(False, "unauthenticated")
    ctx = authz_from_staff(staff)
    if not has_active_org_principal(ctx):
        return AuthDecision(False, "inactive_or_missing_principal")
    if not principal_pg_authz_ready(staff):
        return AuthDecision(False, "pg_capabilities_unavailable")
    if not local_safety_allows_pg_action(staff, resource, action):
        return AuthDecision(False, "local_safety_denied")
    pg_ok = can_pg_action(ctx, resource, action)
    target = (
        int(resource_principal_id)
        if resource_principal_id is not None
        else ctx.principal_id
    )
    return authorize(
        authenticated=True,
        ctx=ctx,
        resource_principal_id=target,
        pg_permission_ok=pg_ok,
        local_safety_ok=True,
    )


def authorize_pg_user_action(
    staff: Mapping[str, Any] | None,
    action: str,
    *,
    resource_principal_id: int | None = None,
) -> AuthDecision:
    if not staff:
        return AuthDecision(False, "unauthenticated")
    ctx = authz_from_staff(staff)
    if not has_active_org_principal(ctx):
        return AuthDecision(False, "inactive_or_missing_principal")
    if not principal_pg_authz_ready(staff):
        return AuthDecision(False, "pg_capabilities_unavailable")
    if not local_safety_allows_pg_action(staff, "users", action):
        return AuthDecision(False, "local_safety_denied")
    pg_ok = can_pg_user_action(ctx, action)
    target = (
        int(resource_principal_id)
        if resource_principal_id is not None
        else ctx.principal_id
    )
    return authorize(
        authenticated=True,
        ctx=ctx,
        resource_principal_id=target,
        pg_permission_ok=pg_ok,
        local_safety_ok=True,
    )


def staff_may_pg_page(staff: Mapping[str, Any] | None, page_key: str) -> bool:
    return authorize_pg_page(staff, page_key).allowed


def staff_may_pg_action(
    staff: Mapping[str, Any] | None,
    resource: str,
    action: str,
    *,
    resource_principal_id: int | None = None,
) -> bool:
    return authorize_pg_action(
        staff,
        resource,
        action,
        resource_principal_id=resource_principal_id,
    ).allowed


def ui_pg_action_flags(staff: Mapping[str, Any] | None) -> dict[str, dict[str, bool]]:
    """UI flags mirroring backend ``staff_may_pg_action`` (N/O parity)."""
    resources = {
        "users": ("create", "update", "delete"),
        "templates": ("create", "update", "delete"),
        "groups": ("create", "update", "delete"),
        "hosts": ("create", "update", "delete"),
        "nodes": ("create", "update", "delete", "reconnect"),
    }
    out: dict[str, dict[str, bool]] = {}
    for res, acts in resources.items():
        out[res] = {act: staff_may_pg_action(staff, res, act) for act in acts}
    return out
