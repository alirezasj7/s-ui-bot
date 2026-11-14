"""Alembic revision: OrgPrincipal.pg_password_enc (Phase 2C).

Revision ID: 0016_org_principal_pg_password
Revises: 0015_org_principal_web_identities
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_org_principal_pg_password"
down_revision: Union[str, None] = "0015_org_principal_web_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    cols = {c["name"] for c in insp.get_columns("org_principals")}
    if "pg_password_enc" in cols:
        return
    op.add_column(
        "org_principals",
        sa.Column("pg_password_enc", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    cols = {c["name"] for c in insp.get_columns("org_principals")}
    if "pg_password_enc" not in cols:
        return
    op.drop_column("org_principals", "pg_password_enc")
