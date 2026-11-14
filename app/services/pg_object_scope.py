"""PasarGuard object scope for hosts/nodes/templates/groups (Phase 1F).

Does not invent ownership metadata. Non-Owner unknown ownership → deny.
Full PG owner (``pg_is_owner``) retains platform object access.

Object checks always use the Principal's own PG client — never authorize
solely because a shared/Owner client could fetch the ID.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.pg_user_scope import is_full_pg_owner, staff_pg_username


def pg_object_owner_username(obj: Mapping[str, Any] | None) -> str:
    """Best-effort owner username from a PG host/node/template/group payload."""
    if not isinstance(obj, Mapping):
        return ""
    admin = obj.get("admin") or obj.get("owner_username") or obj.get("owner") or ""
    if isinstance(admin, Mapping):
        admin = admin.get("username") or ""
    return str(admin or "").strip().lower()


def _id_of(obj: Mapping[str, Any] | None) -> int:
    if not isinstance(obj, Mapping):
        return 0
    try:
        return int(obj.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def pg_object_in_staff_scope(
    obj: Mapping[str, Any] | None,
    staff: Mapping[str, Any] | None,
    *,
    listed_ids: set[int] | None = None,
) -> bool:
    """Whether a loaded PG object belongs to this staff's scope.

    - Full PG owner → allow (platform policy).
    - Explicit owner username on payload → must match staff pg username.
    - No ownership field → only allow when ``listed_ids`` from *this*
      principal's own client enumeration contains the object id.
      Unknown + no list proof → deny (never treat as platform).
    """
    if not isinstance(obj, Mapping) or not staff:
        return False
    oid = _id_of(obj)
    if oid <= 0:
        return False
    if is_full_pg_owner(staff):
        return True

    owned = pg_object_owner_username(obj)
    if owned:
        mine = staff_pg_username(staff)
        if not mine:
            return False
        return owned == mine

    # Unknown ownership metadata — fail closed unless proven via own-client list.
    if listed_ids is None:
        return False
    return oid in listed_ids


async def load_scoped_pg_object(
    pg: Any,
    staff: Mapping[str, Any] | None,
    object_id: int,
    *,
    get_one: str,
    list_all: str,
) -> dict | None:
    """Load one PG object via ``pg`` then enforce object scope (M2).

    ``pg`` must already be the Principal's client (never silently swap to Owner).
    """
    if not staff or int(object_id) <= 0:
        return None
    getter = getattr(pg, get_one, None)
    if getter is None:
        return None
    try:
        raw = await getter(int(object_id))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    if _id_of(raw) != int(object_id):
        return None

    if is_full_pg_owner(staff):
        return raw

    owned = pg_object_owner_username(raw)
    if owned:
        if not pg_object_in_staff_scope(raw, staff):
            return None
        return raw

    # Unknown ownership: prove membership via this client's list.
    listed_ids: set[int] = set()
    lister = getattr(pg, list_all, None)
    if lister is not None:
        try:
            items = await lister()
        except Exception:
            return None
        if isinstance(items, list):
            listed_ids = {_id_of(x) for x in items if isinstance(x, dict)}
        elif isinstance(items, dict):
            # Some PG endpoints wrap lists
            for key in ("hosts", "nodes", "items", "data"):
                inner = items.get(key)
                if isinstance(inner, list):
                    listed_ids = {_id_of(x) for x in inner if isinstance(x, dict)}
                    break
    if not pg_object_in_staff_scope(raw, staff, listed_ids=listed_ids):
        return None
    return raw


async def assert_owned_host(pg: Any, staff: Mapping[str, Any] | None, host_id: int) -> dict | None:
    return await load_scoped_pg_object(
        pg, staff, host_id, get_one="get_host", list_all="get_hosts"
    )


async def assert_owned_node(pg: Any, staff: Mapping[str, Any] | None, node_id: int) -> dict | None:
    return await load_scoped_pg_object(
        pg, staff, node_id, get_one="get_node", list_all="get_nodes"
    )


def inbound_tag_allowed(tag: str | None, valid_tags: set[str] | list[str] | None) -> bool:
    """Host/group inbound tag must appear on this principal's own inbounds."""
    t = str(tag or "").strip()
    if not t:
        return False
    if valid_tags is None:
        return False
    return t in set(valid_tags)
