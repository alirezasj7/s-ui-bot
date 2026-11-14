"""Resource → OrgPrincipal ownership foundation (Phase 1E).

``owner_principal_id`` is the precise scope key for child isolation inside a
reseller shop. ``reseller_id`` remains the tenant compatibility boundary.

Resolution order (never invents):
1. explicit ``owner_principal_id`` on the resource
2. safe legacy map: reseller bot_user_id → unique OrgPrincipal.bot_user_id
3. unknown → None (hierarchy-sensitive access MUST deny)

NULL / unknown ownership must never become global access.
PasarGuard / session role names never affect ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, OrgPrincipal, Ticket, UserService
from app.services.org_principals import STATUS_ACTIVE
from app.services.org_scope import principal_in_scope

ResolutionSource = Literal["explicit", "legacy_reseller", "unknown"]


@dataclass(frozen=True)
class ResourcePrincipalResolution:
    principal_id: int | None
    source: ResolutionSource

    @property
    def is_known(self) -> bool:
        return self.principal_id is not None and int(self.principal_id) > 0


def _positive_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def resolve_resource_principal(
    resource: Any,
    *,
    reseller_bot_user_to_principal: Mapping[int, int] | None = None,
    legacy_reseller_id: int | None = None,
) -> ResourcePrincipalResolution:
    """Resolve owning OrgPrincipal id for a business resource.

    ``legacy_reseller_id`` supplies shop tenant when the resource has no
    ``reseller_id`` column (e.g. UserService via owning BotUser).
    """
    if resource is None:
        return ResourcePrincipalResolution(None, "unknown")

    # 1) Explicit column wins — never overridden by weaker legacy inference.
    explicit = _positive_int(getattr(resource, "owner_principal_id", None))
    if explicit is not None:
        return ResourcePrincipalResolution(explicit, "explicit")

    # 2) Safe legacy: reseller shop bot_user_id → unique principal mapping.
    rid = _positive_int(getattr(resource, "reseller_id", None))
    if rid is None:
        rid = _positive_int(legacy_reseller_id)
    if rid is None:
        return ResourcePrincipalResolution(None, "unknown")

    mapping = reseller_bot_user_to_principal or {}
    mapped = mapping.get(int(rid))
    mapped_id = _positive_int(mapped)
    if mapped_id is None:
        return ResourcePrincipalResolution(None, "unknown")
    return ResourcePrincipalResolution(mapped_id, "legacy_reseller")


def resource_in_principal_scope(
    *,
    actor_visible_principal_ids: frozenset[int] | None,
    resolution: ResourcePrincipalResolution,
) -> bool:
    """Hierarchy-sensitive visibility. Unknown ownership → deny (not global)."""
    if not resolution.is_known:
        return False
    return principal_in_scope(actor_visible_principal_ids, resolution.principal_id)


def build_unique_reseller_bot_user_principal_map(
    principals: list[OrgPrincipal] | None,
) -> dict[int, int]:
    """bot_user_id → principal_id only when exactly one active principal claims it.

    Ambiguous (duplicate bot_user_id) or inactive → omitted (fail closed).
    """
    counts: dict[int, list[int]] = {}
    for p in principals or []:
        if p is None or str(getattr(p, "status", "")) != STATUS_ACTIVE:
            continue
        bot_uid = _positive_int(getattr(p, "bot_user_id", None))
        pid = _positive_int(getattr(p, "id", None))
        if bot_uid is None or pid is None:
            continue
        counts.setdefault(bot_uid, []).append(pid)
    out: dict[int, int] = {}
    for bot_uid, pids in counts.items():
        uniq = sorted(set(pids))
        if len(uniq) == 1:
            out[bot_uid] = uniq[0]
    return out


async def load_reseller_bot_user_principal_map(
    session: AsyncSession,
) -> dict[int, int]:
    result = await session.execute(select(OrgPrincipal))
    return build_unique_reseller_bot_user_principal_map(list(result.scalars().all()))


async def safe_backfill_owner_principal_ids(
    session: AsyncSession,
) -> dict[str, int]:
    """Deterministic backfill only. Never invents child ownership.

    Rules:
    - BotUser / Order / Ticket: ``reseller_id`` → unique principal.bot_user_id
    - UserService: prefer owning BotUser.owner_principal_id if set; else
      BotUser.reseller_id → same unique map
    - Rows with reseller_id NULL stay NULL (platform shop / unresolved)
    - Already-set owner_principal_id is never overwritten
    """
    mapping = await load_reseller_bot_user_principal_map(session)
    updated = {
        "bot_users": 0,
        "orders": 0,
        "tickets": 0,
        "user_services": 0,
        "skipped_ambiguous_or_unmapped": 0,
    }
    if not mapping:
        return updated

    # --- BotUser ---
    users = list(
        (
            await session.execute(
                select(BotUser).where(
                    BotUser.owner_principal_id.is_(None),
                    BotUser.reseller_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for u in users:
        rid = _positive_int(u.reseller_id)
        if rid is None:
            updated["skipped_ambiguous_or_unmapped"] += 1
            continue
        pid = mapping.get(rid)
        if pid is None:
            updated["skipped_ambiguous_or_unmapped"] += 1
            continue
        u.owner_principal_id = int(pid)
        updated["bot_users"] += 1

    # --- Order ---
    orders = list(
        (
            await session.execute(
                select(Order).where(
                    Order.owner_principal_id.is_(None),
                    Order.reseller_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for o in orders:
        rid = _positive_int(o.reseller_id)
        if rid is None or rid not in mapping:
            updated["skipped_ambiguous_or_unmapped"] += 1
            continue
        o.owner_principal_id = int(mapping[rid])
        updated["orders"] += 1

    # --- Ticket ---
    tickets = list(
        (
            await session.execute(
                select(Ticket).where(
                    Ticket.owner_principal_id.is_(None),
                    Ticket.reseller_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for t in tickets:
        rid = _positive_int(t.reseller_id)
        if rid is None or rid not in mapping:
            updated["skipped_ambiguous_or_unmapped"] += 1
            continue
        t.owner_principal_id = int(mapping[rid])
        updated["tickets"] += 1

    # --- UserService (no reseller_id column) ---
    services = list(
        (
            await session.execute(
                select(UserService).where(UserService.owner_principal_id.is_(None))
            )
        )
        .scalars()
        .all()
    )
    if services:
        owner_ids = {int(s.bot_user_id) for s in services if s.bot_user_id}
        owners: dict[int, BotUser] = {}
        if owner_ids:
            rows = list(
                (
                    await session.execute(
                        select(BotUser).where(BotUser.id.in_(list(owner_ids)))
                    )
                )
                .scalars()
                .all()
            )
            owners = {int(u.id): u for u in rows}
        for s in services:
            owner = owners.get(int(s.bot_user_id))
            if owner is None:
                updated["skipped_ambiguous_or_unmapped"] += 1
                continue
            # Prefer already-resolved user principal (may have been backfilled above)
            explicit_user = _positive_int(getattr(owner, "owner_principal_id", None))
            if explicit_user is not None:
                s.owner_principal_id = explicit_user
                updated["user_services"] += 1
                continue
            rid = _positive_int(owner.reseller_id)
            if rid is None or rid not in mapping:
                updated["skipped_ambiguous_or_unmapped"] += 1
                continue
            s.owner_principal_id = int(mapping[rid])
            updated["user_services"] += 1

    await session.flush()
    return updated
