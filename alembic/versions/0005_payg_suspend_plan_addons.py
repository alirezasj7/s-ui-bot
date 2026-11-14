"""PAYG suspend fields + reseller plan add-on switches.

Revision ID: 0005_payg_suspend_plan_addons
Revises: 0004_reseller_plan_payg_rates
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_payg_suspend_plan_addons"
down_revision: Union[str, None] = "0004_reseller_plan_payg_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        if "billing_suspended_at" not in cols:
            op.add_column(
                "reseller_profiles",
                sa.Column("billing_suspended_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "billing_suspended_user_ids" not in cols:
            op.add_column(
                "reseller_profiles",
                sa.Column("billing_suspended_user_ids", sa.Text(), nullable=True),
            )

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "allow_buy_extra" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("allow_buy_extra", sa.Boolean(), server_default="0", nullable=False),
            )
        if "extra_gb_price" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("extra_gb_price", sa.Integer(), server_default="0", nullable=False),
            )
        if "extra_user_price" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("extra_user_price", sa.Integer(), server_default="0", nullable=False),
            )
        if "renew_price" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("renew_price", sa.Integer(), server_default="0", nullable=False),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        for col in ("renew_price", "extra_user_price", "extra_gb_price", "allow_buy_extra"):
            if col in cols:
                op.drop_column("reseller_plans", col)
    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        for col in ("billing_suspended_user_ids", "billing_suspended_at"):
            if col in cols:
                op.drop_column("reseller_profiles", col)
