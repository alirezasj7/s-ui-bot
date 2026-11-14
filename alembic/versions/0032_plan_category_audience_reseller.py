"""Plan category audience + reseller_plans.category_id.

Revision ID: 0032_plan_category_audience_reseller
Revises: 0031_plan_categories_service_addons
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_plan_category_audience_reseller"
down_revision: Union[str, None] = "0031_plan_categories_service_addons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("plan_categories"):
        cols = {c["name"] for c in insp.get_columns("plan_categories")}
        if "audience" not in cols:
            op.add_column(
                "plan_categories",
                sa.Column(
                    "audience",
                    sa.String(length=16),
                    nullable=False,
                    server_default="users",
                ),
            )
            op.create_index(
                "ix_plan_categories_audience",
                "plan_categories",
                ["audience"],
            )

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "category_id" not in cols:
            op.add_column(
                "reseller_plans",
                sa.Column("category_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_reseller_plans_category_id",
                "reseller_plans",
                ["category_id"],
            )
            if insp.has_table("plan_categories"):
                op.create_foreign_key(
                    "fk_reseller_plans_category_id",
                    "reseller_plans",
                    "plan_categories",
                    ["category_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "category_id" in cols:
            try:
                op.drop_constraint(
                    "fk_reseller_plans_category_id",
                    "reseller_plans",
                    type_="foreignkey",
                )
            except Exception:
                pass
            try:
                op.drop_index(
                    "ix_reseller_plans_category_id",
                    table_name="reseller_plans",
                )
            except Exception:
                pass
            op.drop_column("reseller_plans", "category_id")

    if insp.has_table("plan_categories"):
        cols = {c["name"] for c in insp.get_columns("plan_categories")}
        if "audience" in cols:
            try:
                op.drop_index(
                    "ix_plan_categories_audience",
                    table_name="plan_categories",
                )
            except Exception:
                pass
            op.drop_column("plan_categories", "audience")
