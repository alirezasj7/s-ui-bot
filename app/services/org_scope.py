"""Central org scope from Principal hierarchy (Phase 1B / Phase 3A).

Scope is derived only from ``org_principals`` parent/depth — never from
PasarGuard role names or session ``role=admin``.

Phase 3A tree (max depth 2)::

    Owner
    ├── A (depth 1)
    │   ├── A1 (depth 2)
    │   └── A2 (depth 2)
    └── B (depth 1)
        ├── B1 (depth 2)
        └── B2 (depth 2)

Visibility:
  - Owner → every active principal in the organization
  - Level-1 → self + direct active Level-2 children only
  - Level-2 → self only (never parent, never siblings, never other branches)

Level-2 does **not** inherit parent resource visibility. Sibling branches
remain isolated. Missing / inactive / depth>2 → empty set (deny).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OrgPrincipal
from app.services.org_principals import (
    DEPTH_OWNER,
    DEPTH_ONE,
    DEPTH_TWO,
    MAX_DEPTH,
    STATUS_ACTIVE,
    is_owner_principal,
)


def _active(p: OrgPrincipal | None) -> bool:
    return p is not None and str(getattr(p, "status", "")) == STATUS_ACTIVE


def scope_ids_for_principal(
    principal: OrgPrincipal | None,
    *,
    all_principals: Sequence[OrgPrincipal],
) -> frozenset[int]:
    """Pure scope calculation over an in-memory principal set.

    - Owner (depth 0): every active principal in the organization
    - Depth 1: self + active descendants (depth-2 with parent=self)
    - Depth 2: self only (requires active Level-1 parent; else empty)
    - Inactive / missing / depth>2: empty (deny)
    """
    if principal is None or not _active(principal):
        return frozenset()
    try:
        depth = int(principal.depth)
    except (TypeError, ValueError):
        return frozenset()
    if depth < DEPTH_OWNER or depth > MAX_DEPTH:
        return frozenset()

    by_id = {int(p.id): p for p in all_principals if getattr(p, "id", None) is not None}

    if depth == DEPTH_OWNER:
        if not is_owner_principal(principal):
            return frozenset()
        return frozenset(
            int(p.id)
            for p in all_principals
            if _active(p) and getattr(p, "id", None) is not None
        )

    self_id = int(principal.id)
    if depth == DEPTH_ONE:
        kids = {
            int(p.id)
            for p in all_principals
            if _active(p)
            and int(getattr(p, "depth", -1) or -1) == DEPTH_TWO
            and int(getattr(p, "parent_id", 0) or 0) == self_id
        }
        return frozenset({self_id}) | kids

    # depth 2 — self only; never parent / siblings / cross-branch.
    # Orphan or inactive / non-L1 parent → fail closed (empty).
    parent_id = getattr(principal, "parent_id", None)
    if parent_id is None:
        return frozenset()
    parent = by_id.get(int(parent_id))
    if parent is None or not _active(parent) or int(parent.depth) != DEPTH_ONE:
        return frozenset()
    return frozenset({self_id})


def principal_in_scope(
    visible_ids: Iterable[int] | None,
    target_principal_id: int | None,
) -> bool:
    """Object-level principal membership. Missing target or empty visible → deny."""
    if target_principal_id is None:
        return False
    try:
        tid = int(target_principal_id)
    except (TypeError, ValueError):
        return False
    if tid <= 0:
        return False
    visible = frozenset(int(x) for x in (visible_ids or ()))
    if not visible:
        return False
    return tid in visible


async def load_all_principals(session: AsyncSession) -> list[OrgPrincipal]:
    result = await session.execute(select(OrgPrincipal))
    return list(result.scalars().all())


async def visible_principal_ids(
    session: AsyncSession,
    principal: OrgPrincipal | None,
) -> frozenset[int]:
    """DB-backed visible set for ``principal``. Empty when missing/inactive."""
    if principal is None or not _active(principal):
        return frozenset()
    rows = await load_all_principals(session)
    return scope_ids_for_principal(principal, all_principals=rows)


async def assert_principal_in_scope(
    session: AsyncSession,
    actor: OrgPrincipal | None,
    target_principal_id: int | None,
) -> bool:
    """True iff target is in actor's visible set (fail-closed)."""
    visible = await visible_principal_ids(session, actor)
    return principal_in_scope(visible, target_principal_id)
