"""Add is_system flag on reseller_plans (current-capacity seed).

Revision ID: 0043_reseller_plan_is_system
Revises: 0042_pg_api_key_enc
Create Date: 2026-10-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_reseller_plan_is_system"
down_revision: Union[str, None] = "0042_pg_api_key_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_plans"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_plans")}
    if "is_system" not in cols:
        op.add_column(
            "reseller_plans",
            sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_plans"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_plans")}
    if "is_system" in cols:
        op.drop_column("reseller_plans", "is_system")
