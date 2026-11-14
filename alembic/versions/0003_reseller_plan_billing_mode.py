"""Add billing_mode to reseller_plans (and profile billing columns).

Revision ID: 0003_reseller_plan_billing_mode
Revises: 0002_pg_staff_credentials
Create Date: 2026-08-04

v4.0.5 added ResellerPlan.billing_mode on the ORM and in the legacy additive
migrator, but Alembic-managed production DBs never ran that path after stamp —
SELECT on /plans then 500'd with \"no such column: billing_mode\".
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_reseller_plan_billing_mode"
down_revision: Union[str, None] = "0002_pg_staff_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "billing_mode" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("billing_mode", sa.String(16), server_default="fixed", nullable=False),
            )

    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        profile_alters = [
            ("billing_mode", sa.Column("billing_mode", sa.String(16), server_default="fixed")),
            ("billing_balance", sa.Column("billing_balance", sa.Integer(), server_default="0")),
            (
                "billing_watermark_bytes",
                sa.Column("billing_watermark_bytes", sa.BigInteger(), server_default="0"),
            ),
            ("billing_low_warned_at", sa.Column("billing_low_warned_at", sa.DateTime(timezone=True))),
        ]
        for name, col in profile_alters:
            if name not in cols:
                op.add_column("reseller_profiles", col)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_profiles"):
        cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        for name in (
            "billing_low_warned_at",
            "billing_watermark_bytes",
            "billing_balance",
            "billing_mode",
        ):
            if name in cols:
                op.drop_column("reseller_profiles", name)

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "billing_mode" in cols:
            op.drop_column("reseller_plans", "billing_mode")
