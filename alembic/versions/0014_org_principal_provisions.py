"""Alembic revision: org_principal_provisions idempotency ledger (Phase 2A).

Revision ID: 0014_org_principal_provisions
Revises: 0013_resource_owner_principal
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_org_principal_provisions"
down_revision: Union[str, None] = "0013_resource_owner_principal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principal_provisions"):
        return

    op.create_table(
        "org_principal_provisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "principal_id",
            sa.Integer(),
            sa.ForeignKey("org_principals.id"),
            nullable=False,
        ),
        sa.Column("pg_username", sa.String(128), nullable=False),
        sa.Column("pg_role_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_by_principal_id",
            sa.Integer(),
            sa.ForeignKey("org_principals.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), server_default="completed", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_org_principal_provision_idem"),
    )
    op.create_index(
        "ix_org_principal_provisions_principal_id",
        "org_principal_provisions",
        ["principal_id"],
    )
    op.create_index(
        "ix_org_principal_provisions_pg_username",
        "org_principal_provisions",
        ["pg_username"],
    )
    op.create_index(
        "ix_org_principal_provisions_created_by_principal_id",
        "org_principal_provisions",
        ["created_by_principal_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principal_provisions"):
        op.drop_table("org_principal_provisions")
