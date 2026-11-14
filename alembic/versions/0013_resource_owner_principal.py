"""Alembic revision: owner_principal_id on prioritized business resources (Phase 1E).

Revision ID: 0013_resource_owner_principal
Revises: 0012_org_principals
Create Date: 2026-08-16

Adds nullable owner_principal_id only to BotUser, Order, Ticket, UserService.
Does NOT invent backfill values — backfill is an explicit service call that
maps reseller_id → OrgPrincipal only when deterministic.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_resource_owner_principal"
down_revision: Union[str, None] = "0012_org_principals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    ("bot_users", "ix_bot_users_owner_principal_id"),
    ("orders", "ix_orders_owner_principal_id"),
    ("tickets", "ix_tickets_owner_principal_id"),
    ("user_services", "ix_user_services_owner_principal_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table, index_name in _TABLES:
        if not insp.has_table(table):
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "owner_principal_id" in cols:
            continue
        op.add_column(
            table,
            sa.Column(
                "owner_principal_id",
                sa.Integer(),
                sa.ForeignKey("org_principals.id"),
                nullable=True,
            ),
        )
        op.create_index(index_name, table, ["owner_principal_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table, index_name in reversed(_TABLES):
        if not insp.has_table(table):
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "owner_principal_id" not in cols:
            continue
        try:
            op.drop_index(index_name, table_name=table)
        except Exception:
            pass
        op.drop_column(table, "owner_principal_id")
