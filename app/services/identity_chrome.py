"""UI-only hierarchy identity labels and capability chips.

Does not grant access, change scope, or map PasarGuard permissions.
Reads already-attached staff fields (org_depth, pg_permissions, pg_role_name).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.pg_access import PG_FEATURE_LABELS

# Display order for confirmed PG feature keys. pg_admins is Owner-only UI — omit here.
_CHIP_ORDER = (
    "pg_users",
    "pg_nodes",
    "pg_hosts",
    "pg_templates",
    "pg_groups",
    "pg_inbounds",
    "pg_overview",
)


def principal_capability_chips(staff: Mapping[str, Any] | None) -> list[str]:
    """Short labels for confirmed ``pg_permissions`` only. Fail closed if missing."""
    if not staff:
        return []
    raw = staff.get("pg_permissions")
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []
    confirmed = {str(k) for k in raw if k}
    out: list[str] = []
    for key in _CHIP_ORDER:
        if key not in confirmed:
            continue
        label = PG_FEATURE_LABELS.get(key)
        if label:
            out.append(label)
    return out


def _depth_int(staff: Mapping[str, Any]) -> int | None:
    raw = staff.get("org_depth")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _live_pg_role_name(staff: Mapping[str, Any]) -> str | None:
    name = staff.get("pg_role_name")
    if not isinstance(name, str):
        return None
    cleaned = name.strip()
    return cleaned or None


def hierarchy_identity(staff: Mapping[str, Any] | None) -> dict[str, Any]:
    """Presentation dict for sidebar/footer. Never used as an authorization gate."""
    empty: dict[str, Any] = {
        "kind": None,
        "label": None,
        "pg_role_name": None,
        "show_pg_role": False,
        "chips": [],
        "commercial_reseller": False,
        "can_add_representative": False,
        "can_manage_representatives": False,
    }
    if not staff:
        return empty

    from app.services.platform_identity import is_explicit_owner_staff
    from app.services.representative_unification import staff_can_manage_representatives

    can_manage = staff_can_manage_representatives(staff)
    can_add = (not is_explicit_owner_staff(staff)) and can_manage

    if is_explicit_owner_staff(staff):
        return {
            "kind": "owner",
            "label": "مالک",
            "pg_role_name": None,
            "show_pg_role": False,
            "chips": [],
            "commercial_reseller": False,
            "can_add_representative": False,
            "can_manage_representatives": can_manage,
        }

    role = str(staff.get("role") or "").strip()
    depth = _depth_int(staff)
    pg_name = _live_pg_role_name(staff)

    # Shop reseller stays a commercial label even when an adapter Principal exists.
    if role == "reseller":
        return {
            "kind": "reseller",
            "label": "نماینده",
            "pg_role_name": None,
            "show_pg_role": False,
            "chips": [],
            "commercial_reseller": True,
            "can_add_representative": can_add,
            "can_manage_representatives": can_manage,
        }

    if role == "principal" or (depth in (1, 2) and role not in {"reseller", "admin"}):
        if depth == 2:
            kind, label = "l2", "زیرنماینده"
        elif depth == 1:
            kind, label = "l1", "نماینده"
        else:
            kind, label = "principal", None
        chips = principal_capability_chips(staff) if kind in {"l1", "l2"} else []
        return {
            "kind": kind,
            "label": label,
            "pg_role_name": pg_name,
            "show_pg_role": bool(pg_name),
            "chips": chips,
            "commercial_reseller": False,
            "can_add_representative": can_add,
            "can_manage_representatives": can_manage,
        }

    if role == "pg_staff":
        return {
            "kind": "pg_staff",
            "label": "ادمین پاسارگارد",
            "pg_role_name": None,
            "show_pg_role": False,
            "chips": [],
            "commercial_reseller": False,
            "can_add_representative": False,
            "can_manage_representatives": False,
        }

    if role == "admin":
        return {
            "kind": "admin_label",
            "label": "ادمین",
            "pg_role_name": None,
            "show_pg_role": False,
            "chips": [],
            "commercial_reseller": False,
            "can_add_representative": False,
            "can_manage_representatives": False,
        }

    return empty


def principal_web_uses_pg_home(staff: Mapping[str, Any] | None) -> bool:
    """True when a Principal-web L1/L2 (not a shop reseller) should land on /pg."""
    if not staff:
        return False
    if str(staff.get("role") or "").strip() != "principal":
        return False
    depth = _depth_int(staff)
    if depth not in (1, 2):
        return False
    from app.services.shop_scope import shop_owner_id

    return shop_owner_id(staff) is None


def resolve_staff_home(staff: Mapping[str, Any] | None) -> tuple[str, str]:
    """Presentation router for /home. Returns (\"template\"|\"redirect\", value)."""
    from app.services.shop_scope import is_platform_admin, shop_owner_id

    if not staff:
        return ("redirect", "/login")
    if is_platform_admin(staff):
        return ("template", "home.html")
    if principal_web_uses_pg_home(staff):
        return ("redirect", "/pg")
    rid = shop_owner_id(staff)
    if rid:
        return ("template", "reseller_home.html")
    if staff.get("pg_permissions"):
        return ("redirect", "/pg")
    return ("redirect", "/security")
