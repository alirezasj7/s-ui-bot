"""Add PG credential columns to pg_staff_access (Phase C5).

Revision ID: 0002_pg_staff_credentials
Revises: 0001_baseline
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_pg_staff_credentials"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("pg_staff_access"):
        return
    cols = {c["name"] for c in insp.get_columns("pg_staff_access")}
    if "pg_admin_password_enc" not in cols:
        op.add_column(
            "pg_staff_access",
            sa.Column("pg_admin_password_enc", sa.Text(), nullable=True),
        )
    if "pg_role_id" not in cols:
        op.add_column(
            "pg_staff_access",
            sa.Column("pg_role_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("pg_staff_access"):
        return
    cols = {c["name"] for c in insp.get_columns("pg_staff_access")}
    if "pg_role_id" in cols:
        op.drop_column("pg_staff_access", "pg_role_id")
    if "pg_admin_password_enc" in cols:
        op.drop_column("pg_staff_access", "pg_admin_password_enc")
