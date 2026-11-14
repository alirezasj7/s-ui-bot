"""Bot PG node/host authorization (shared with Web Authz).

Telegram identity → OrgPrincipal → AuthzContext → live PG capability
→ object scope (pg_object_scope) → local safety → action.

Nodes and hosts often have no explicit owner field. Ownership is proven only
when:

- the Principal is a full PG owner, or
- an owner username on the payload matches the Principal's PG username, or
- the object id appears in this Principal's own PG list.

Missing owner / missing metadata is never treated as global ownership.

Callback/message data may carry a resource id only. Hierarchy / PG identity
fields are ignored and treated as tamper → DENY.

Shop bots are isolated. Bound L2 uses the same node/host gate as L1 with
self-only object scope and ``get_pg_for_principal(L2.id)``.

Host authorization uses the same gate as nodes so list/read/mutate can be
tested and reused without inventing new permission names or a second RBAC.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser
from app.services.authz import AuthDecision
from app.services.bot_principal_identity import (
    BotPrincipalResolution,
    bot_pg_client_for_resolution,
    callback_carries_principal_tamper,
    resolve_bot_pg_family_identity,
)
from app.services.pg_object_scope import (
    assert_owned_host,
    assert_owned_node,
    pg_object_in_staff_scope,
)
from app.services.principal_pg_authz import (
    apply_level1_pg_local_safety,
    authorize_pg_action,
    authorize_pg_page,
    is_level1_principal_staff,
    principal_pg_authz_ready,
)
from app.services import bot_feedback_texts as feedback

BotPgObjectKind = Literal["nodes", "hosts"]
BotPgObjectAction = Literal["list", "read", "create", "update", "delete", "reconnect"]

_COLLECTION_ACTIONS = frozenset({"list", "create"})
_PAGE_KEY = {"nodes": "pg_nodes", "hosts": "pg_hosts"}
_PG_RESOURCE = {"nodes": "nodes", "hosts": "hosts"}

_NODE_DETAIL_RE = re.compile(r"^adm:pg:n:(\d+)$")
_NODE_RECON_RE = re.compile(r"^adm:pg:recon:(\d+)$")
_NODE_SYNC_RE = re.compile(r"^adm:pg:nsync:(\d+)$")
_NODE_RESETASK_RE = re.compile(r"^adm:pg:nresetask:(\d+)$")
_NODE_RESET_RE = re.compile(r"^adm:pg:nreset:(\d+)$")
_NODE_TOG_RE = re.compile(r"^adm:pg:ntog:(\d+)$")
_NODE_DELASK_RE = re.compile(r"^adm:pg:ndelask:(\d+)$")
_NODE_DEL_RE = re.compile(r"^adm:pg:ndel:(\d+)$")

_ACTION_ID_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "read": (_NODE_DETAIL_RE,),
    "reconnect": (_NODE_RECON_RE, _NODE_SYNC_RE),
    "update": (_NODE_RESETASK_RE, _NODE_RESET_RE, _NODE_TOG_RE),
    "delete": (_NODE_DELASK_RE, _NODE_DEL_RE),
}

_TAMPER_NEEDLES = (
    "pg_username",
    "pg_admin",
    "parent_id",
    "org_scope",
    "org_visible",
    "web_owner",
    "org_depth",
    "org_principal",
    "org_parent",
    "principal_id",
    "depth=",
)

_CLIENT_OWNER_KEYS = (
    "admin",
    "owner",
    "owner_username",
    "admin_username",
    "org_principal_id",
    "parent_id",
    "org_parent_id",
    "org_depth",
    "web_owner",
    "org_scope",
    "principal_id",
    "pg_username",
)

_USER_MESSAGES = {
    "unauthenticated": feedback.NOT_ADMIN,
    "shop_bot_isolated": feedback.NOT_ADMIN,
    "identity_tamper": feedback.ACTION_NOT_ALLOWED,
    "inactive_or_missing_principal": feedback.NOT_ADMIN,
    "missing_principal": feedback.NOT_ADMIN,
    "pg_permission_denied": feedback.ACTION_NOT_ALLOWED,
    "pg_capabilities_unavailable": feedback.ACTION_NOT_ALLOWED,
    "resource_out_of_scope": feedback.ACTION_NOT_ALLOWED,
    "resource_not_found": feedback.ACTION_NOT_ALLOWED,
    "pg_outage": feedback.ACTION_NOT_ALLOWED,
    "local_safety_denied": feedback.ACTION_NOT_ALLOWED,
    "invalid_resource": feedback.ACTION_NOT_ALLOWED,
    "missing_scope": feedback.ACTION_NOT_ALLOWED,
    "unsupported_kind": feedback.ACTION_NOT_ALLOWED,
}


@dataclass(frozen=True)
class BotPgObjectGate:
    allowed: bool
    reason: str
    user_message: str
    resolution: BotPrincipalResolution | None = None
    staff: dict[str, Any] | None = None
    pg_object: dict[str, Any] | None = None
    pg_client: Any = None
    kind: str = ""
    as_owner_client: bool = False


def _deny(
    reason: str,
    *,
    resolution: BotPrincipalResolution | None = None,
    kind: str = "",
) -> BotPgObjectGate:
    return BotPgObjectGate(
        allowed=False,
        reason=reason,
        user_message=_USER_MESSAGES.get(reason, feedback.ACTION_NOT_ALLOWED),
        resolution=resolution,
        kind=kind,
    )


def callback_carries_identity_tamper(callback_data: str | None) -> bool:
    """True when callback tries to inject principal / PG identity fields."""
    if callback_carries_principal_tamper(callback_data):
        return True
    if not callback_data:
        return False
    lowered = str(callback_data).lower()
    return any(needle in lowered for needle in _TAMPER_NEEDLES)


def parse_pg_object_callback_id(
    callback_data: str | None, *, action: BotPgObjectAction
) -> int | None:
    """Extract node id from a strict callback pattern. Extra fields → None."""
    if not callback_data:
        return None
    raw = str(callback_data).strip()
    patterns = _ACTION_ID_PATTERNS.get(str(action)) or ()
    for match_re in patterns:
        match = match_re.match(raw)
        if match is None:
            continue
        try:
            oid = int(match.group(1))
        except (TypeError, ValueError):
            return None
        return oid if oid > 0 else None
    return None


def sanitize_pg_object_write_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop client-supplied owner/scope fields — Principal identity is server-side."""
    if not isinstance(payload, dict):
        return {}
    out = dict(payload)
    for key in _CLIENT_OWNER_KEYS:
        out.pop(key, None)
    return out


def _prepare_staff(resolution: BotPrincipalResolution) -> dict[str, Any] | None:
    staff = dict(resolution.staff)
    if is_level1_principal_staff(staff):
        staff = apply_level1_pg_local_safety(staff)
    if not principal_pg_authz_ready(staff):
        return None
    return staff


def _capability_decision(
    staff: dict[str, Any],
    *,
    kind: BotPgObjectKind,
    action: BotPgObjectAction,
) -> AuthDecision:
    page_key = _PAGE_KEY.get(str(kind))
    resource = _PG_RESOURCE.get(str(kind))
    if not page_key or not resource:
        return AuthDecision(False, "unsupported_kind")
    if action in {"list", "read"}:
        return authorize_pg_page(staff, page_key)
    if action == "reconnect" and kind != "nodes":
        return AuthDecision(False, "pg_permission_denied")
    return authorize_pg_action(staff, resource, str(action))


async def _resolve_identity(
    session: AsyncSession | None,
    *,
    db_user: BotUser | None,
    is_reseller_bot: bool,
    reseller_profile_id: int | None,
    reseller_owner_id: int | None,
    callback_data: str | None,
) -> BotPgObjectGate | BotPrincipalResolution:
    if session is None or db_user is None:
        return _deny("unauthenticated")
    got = await resolve_bot_pg_family_identity(
        session,
        db_user=db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_profile_id=reseller_profile_id,
        reseller_owner_id=reseller_owner_id,
        identity_tamper=callback_carries_identity_tamper(callback_data),
    )
    if isinstance(got, str):
        return _deny(got)
    return got


def _unwrap_object_list(raw: Any, kind: str) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, dict):
        return []
    keys = (kind, "items", "data")
    if kind == "nodes":
        keys = ("nodes", "items", "data")
    elif kind == "hosts":
        keys = ("hosts", "items", "data")
    for key in keys:
        inner = raw.get(key)
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _id_of(obj: Mapping[str, Any] | None) -> int:
    if not isinstance(obj, Mapping):
        return 0
    try:
        return int(obj.get("id") or 0)
    except (TypeError, ValueError):
        return 0


async def authorize_bot_pg_object_op(
    session: AsyncSession | None,
    *,
    db_user: BotUser | None,
    kind: BotPgObjectKind,
    action: BotPgObjectAction,
    callback_data: str | None = None,
    object_id: int | None = None,
    is_reseller_bot: bool = False,
    reseller_profile_id: int | None = None,
    reseller_owner_id: int | None = None,
) -> BotPgObjectGate:
    """Authorize a Bot node/host operation (collection or ID-based)."""
    if kind not in {"nodes", "hosts"}:
        return _deny("unsupported_kind")

    ident = await _resolve_identity(
        session,
        db_user=db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_profile_id=reseller_profile_id,
        reseller_owner_id=reseller_owner_id,
        callback_data=callback_data,
    )
    if isinstance(ident, BotPgObjectGate):
        return ident
    resolution = ident

    staff = _prepare_staff(resolution)
    if staff is None:
        return _deny("pg_capabilities_unavailable", resolution=resolution, kind=kind)

    cap = _capability_decision(staff, kind=kind, action=action)
    if not cap.allowed:
        return BotPgObjectGate(
            allowed=False,
            reason=cap.reason or "pg_permission_denied",
            user_message=_USER_MESSAGES.get(
                cap.reason, _USER_MESSAGES["pg_permission_denied"]
            ),
            resolution=resolution,
            staff=staff,
            kind=kind,
        )

    try:
        pg_client, as_owner = await bot_pg_client_for_resolution(session, resolution)
    except Exception:
        return _deny("pg_outage", resolution=resolution, kind=kind)

    oid = object_id
    if oid is None and action not in _COLLECTION_ACTIONS:
        oid = parse_pg_object_callback_id(callback_data, action=action)

    collection = action in _COLLECTION_ACTIONS
    if action == "reconnect" and oid is None:
        # Collection reconnect-all uses the Principal's own client (no ID).
        if callback_data in {None, "", "adm:pg:nreconall"}:
            collection = True
        else:
            return _deny("invalid_resource", resolution=resolution, kind=kind)

    if collection:
        return BotPgObjectGate(
            allowed=True,
            reason="ok",
            user_message="",
            resolution=resolution,
            staff=staff,
            pg_client=pg_client,
            kind=kind,
            as_owner_client=bool(as_owner),
        )

    try:
        oid_i = int(oid) if oid is not None else 0
    except (TypeError, ValueError):
        oid_i = 0
    if oid_i <= 0:
        return _deny("invalid_resource", resolution=resolution, kind=kind)

    getter_name = "get_node" if kind == "nodes" else "get_host"
    getter = getattr(pg_client, getter_name, None)
    if getter is None:
        return _deny("pg_outage", resolution=resolution, kind=kind)
    try:
        raw = await getter(oid_i)
    except Exception:
        return _deny("pg_outage", resolution=resolution, kind=kind)
    if not isinstance(raw, dict):
        return _deny("resource_not_found", resolution=resolution, kind=kind)

    loader = assert_owned_node if kind == "nodes" else assert_owned_host
    try:
        scoped = await loader(pg_client, staff, oid_i)
    except Exception:
        return _deny("pg_outage", resolution=resolution, kind=kind)
    if scoped is None:
        return _deny("resource_out_of_scope", resolution=resolution, kind=kind)

    return BotPgObjectGate(
        allowed=True,
        reason="ok",
        user_message="",
        resolution=resolution,
        staff=staff,
        pg_object=scoped,
        pg_client=pg_client,
        kind=kind,
        as_owner_client=bool(as_owner),
    )


async def list_scoped_pg_objects(
    gate: BotPgObjectGate,
    *,
    kind: BotPgObjectKind | None = None,
) -> list[dict[str, Any]]:
    """Fetch via the Principal's own client, then keep only in-scope objects."""
    if not gate.allowed or gate.pg_client is None or gate.staff is None:
        return []
    use_kind = str(kind or gate.kind or "")
    if use_kind not in {"nodes", "hosts"}:
        return []
    lister_name = "get_nodes" if use_kind == "nodes" else "get_hosts"
    lister = getattr(gate.pg_client, lister_name, None)
    if lister is None:
        return []
    raw = await lister()
    items = _unwrap_object_list(raw, use_kind)
    listed_ids = {_id_of(x) for x in items if _id_of(x) > 0}
    return [
        x
        for x in items
        if pg_object_in_staff_scope(x, gate.staff, listed_ids=listed_ids)
    ]
