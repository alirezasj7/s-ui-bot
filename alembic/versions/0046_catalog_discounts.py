"""Add shop catalog price adjustments and announcement references."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_catalog_discounts"
down_revision = "0045_plan_category_icon_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("catalog_discounts"):
        op.create_table(
            "catalog_discounts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("shop_key", sa.Integer(), nullable=False),
            sa.Column("reseller_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=True),
            sa.Column("active_slot", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(128), nullable=False),
            sa.Column("scope", sa.String(16), nullable=False),
            sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="SET NULL"), nullable=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("plan_categories.id", ondelete="SET NULL"), nullable=True),
            sa.Column("mode", sa.String(16), nullable=False),
            sa.Column("reduction_kind", sa.String(16), nullable=False),
            sa.Column("reduction_value", sa.Integer(), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("request_key", sa.String(32), nullable=False),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("targeted_campaigns.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("shop_key", "request_key", name="uq_catalog_discount_request"),
            sa.UniqueConstraint("shop_key", "active_slot", name="uq_catalog_discount_slot"),
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("catalog_discounts")}
    for name, columns in (
        ("ix_catalog_discounts_shop_active", ["shop_key", "is_active", "ends_at"]),
        ("ix_catalog_discounts_shop_history", ["shop_key", "id"]),
        ("ix_catalog_discounts_campaign", ["campaign_id"]),
    ):
        if name not in indexes:
            op.create_index(name, "catalog_discounts", columns)


def downgrade() -> None:
    # Keep adjustment history and all catalog/customer rows during rollback.
    # Older releases ignore this additive table; a later upgrade can reuse it.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("catalog_discounts"):
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes("catalog_discounts")}
        for name in ("ix_catalog_discounts_shop_active", "ix_catalog_discounts_shop_history", "ix_catalog_discounts_campaign"):
            if name in indexes:
                op.drop_index(name, table_name="catalog_discounts")
