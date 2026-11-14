"""Alembic revision: org_principals hierarchy foundation (Phase 1A).

Revision ID: 0012_org_principals
Revises: 0011_pg_admin_subscription
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_org_principals"
down_revision: Union[str, None] = "0011_pg_admin_subscription"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principals"):
        return

    op.create_table(
        "org_principals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("org_principals.id"), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("pg_username", sa.String(128), nullable=True),
        sa.Column(
            "reseller_profile_id",
            sa.Integer(),
            sa.ForeignKey("reseller_profiles.id"),
            nullable=True,
        ),
        sa.Column(
            "pg_staff_id",
            sa.Integer(),
            sa.ForeignKey("pg_staff_access.id"),
            nullable=True,
        ),
        sa.Column("bot_user_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("reseller_profile_id", name="uq_org_principals_reseller_profile"),
        sa.UniqueConstraint("pg_staff_id", name="uq_org_principals_pg_staff"),
    )
    op.create_index("ix_org_principals_parent_id", "org_principals", ["parent_id"])
    op.create_index("ix_org_principals_depth", "org_principals", ["depth"])
    op.create_index("ix_org_principals_status", "org_principals", ["status"])
    op.create_index("ix_org_principals_pg_username", "org_principals", ["pg_username"])
    op.create_index("ix_org_principals_bot_user_id", "org_principals", ["bot_user_id"])

    # Seed single active Owner — not derived from role=admin
    op.execute(
        sa.text(
            "INSERT INTO org_principals "
            "(parent_id, depth, status, pg_username, reseller_profile_id, pg_staff_id, bot_user_id) "
            "VALUES (NULL, 0, 'active', NULL, NULL, NULL, NULL)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principals"):
        op.drop_table("org_principals")
