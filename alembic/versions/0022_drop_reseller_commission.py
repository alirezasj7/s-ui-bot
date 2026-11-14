"""Drop legacy reseller fixed-mode commission columns.

Revision ID: 0022_drop_reseller_commission
Revises: 0021_payment_settlements
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_drop_reseller_commission"
down_revision: Union[str, None] = "0021_payment_settlements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        if "commission_percent" in cols:
            op.drop_column("reseller_profiles", "commission_percent")
        if "balance" in cols:
            op.drop_column("reseller_profiles", "balance")

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "commission_percent" in cols:
            op.drop_column("reseller_plans", "commission_percent")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        if "commission_percent" not in cols:
            op.add_column(
                "reseller_profiles",
                sa.Column("commission_percent", sa.Integer(), server_default="10", nullable=False),
            )
        if "balance" not in cols:
            op.add_column(
                "reseller_profiles",
                sa.Column("balance", sa.Integer(), server_default="0", nullable=False),
            )

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "commission_percent" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("commission_percent", sa.Integer(), server_default="0", nullable=False),
            )
