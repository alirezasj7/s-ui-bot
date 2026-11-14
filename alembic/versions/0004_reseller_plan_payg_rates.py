"""Add PAYG per-plan price_per_gb and pg_group_ids on reseller_plans.

Revision ID: 0004_reseller_plan_payg_rates
Revises: 0003_reseller_plan_billing_mode
Create Date: 2026-08-04

Enables multiple PAYG reseller packages with different usage rates
(e.g. different PasarGuard group pricing tiers).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_reseller_plan_payg_rates"
down_revision: Union[str, None] = "0003_reseller_plan_billing_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_plans"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_plans")}
    if "price_per_gb" not in cols:
        op.add_column(
            "reseller_plans",
            sa.Column("price_per_gb", sa.Integer(), server_default="0", nullable=False),
        )
    if "pg_group_ids" not in cols:
        op.add_column(
            "reseller_plans",
            sa.Column("pg_group_ids", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_plans"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_plans")}
    if "pg_group_ids" in cols:
        op.drop_column("reseller_plans", "pg_group_ids")
    if "price_per_gb" in cols:
        op.drop_column("reseller_plans", "price_per_gb")
