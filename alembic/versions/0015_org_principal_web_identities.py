"""Alembic revision: org_principal_web_identities (Phase 2B).

Revision ID: 0015_org_principal_web_identities
Revises: 0014_org_principal_provisions
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_org_principal_web_identities"
down_revision: Union[str, None] = "0014_org_principal_provisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principal_web_identities"):
        return

    op.create_table(
        "org_principal_web_identities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "principal_id",
            sa.Integer(),
            sa.ForeignKey("org_principals.id"),
            nullable=False,
        ),
        sa.Column("web_username", sa.String(128), nullable=False),
        sa.Column("web_password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("principal_id", name="uq_org_principal_web_identity_principal"),
        sa.UniqueConstraint("web_username", name="uq_org_principal_web_identity_username"),
    )
    op.create_index(
        "ix_org_principal_web_identities_principal_id",
        "org_principal_web_identities",
        ["principal_id"],
    )
    op.create_index(
        "ix_org_principal_web_identities_web_username",
        "org_principal_web_identities",
        ["web_username"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("org_principal_web_identities"):
        op.drop_table("org_principal_web_identities")
