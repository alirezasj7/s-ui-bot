"""Plan categories + customer service addon packs.

Revision ID: 0031_plan_categories_service_addons
Revises: 0030_legacy_wallet_isolation_repair
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_plan_categories_service_addons"
down_revision: Union[str, None] = "0030_legacy_wallet_isolation_repair"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("plan_categories"):
        op.create_table(
            "plan_categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("owner_reseller_id", sa.Integer(), nullable=True),
            # sa.true()/false() → DEFAULT true/false on PostgreSQL; 1/0 on SQLite.
            # Literal integer boolean defaults are rejected by PostgreSQL and
            # abort panel startup (uvicorn exit 3) during upgrade to 0.2.0.
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["owner_reseller_id"], ["bot_users.id"]),
        )
        op.create_index(
            "ix_plan_categories_owner_reseller_id",
            "plan_categories",
            ["owner_reseller_id"],
        )

    if insp.has_table("plans"):
        cols = {c["name"] for c in insp.get_columns("plans")}
        if "category_id" not in cols:
            op.add_column(
                "plans",
                sa.Column("category_id", sa.Integer(), nullable=True),
            )
            op.create_index("ix_plans_category_id", "plans", ["category_id"])
            op.create_foreign_key(
                "fk_plans_category_id",
                "plans",
                "plan_categories",
                ["category_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if not insp.has_table("service_addon_packs"):
        op.create_table(
            "service_addon_packs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("price", sa.Integer(), nullable=False),
            sa.Column("owner_reseller_id", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["owner_reseller_id"], ["bot_users.id"]),
        )
        op.create_index(
            "ix_service_addon_packs_owner_reseller_id",
            "service_addon_packs",
            ["owner_reseller_id"],
        )
        op.create_index("ix_service_addon_packs_kind", "service_addon_packs", ["kind"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("plans"):
        cols = {c["name"] for c in insp.get_columns("plans")}
        if "category_id" in cols:
            try:
                op.drop_constraint("fk_plans_category_id", "plans", type_="foreignkey")
            except Exception:
                pass
            try:
                op.drop_index("ix_plans_category_id", table_name="plans")
            except Exception:
                pass
            op.drop_column("plans", "category_id")

    if insp.has_table("service_addon_packs"):
        op.drop_table("service_addon_packs")
    if insp.has_table("plan_categories"):
        op.drop_table("plan_categories")
