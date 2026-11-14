"""Loyalty discount entitlements + reward constraint columns.

Revision ID: 0008_loyalty_discounts
Revises: 0007_referral_loyalty
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_loyalty_discounts"
down_revision: Union[str, None] = "0007_referral_loyalty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("loyalty_rewards"):
        cols = {c["name"] for c in insp.get_columns("loyalty_rewards")}
        if "min_purchase_toman" not in cols:
            op.add_column(
                "loyalty_rewards",
                sa.Column("min_purchase_toman", sa.Integer(), server_default="0", nullable=False),
            )
        if "max_discount_toman" not in cols:
            op.add_column(
                "loyalty_rewards",
                sa.Column("max_discount_toman", sa.Integer(), nullable=True),
            )
        if "expires_days" not in cols:
            op.add_column(
                "loyalty_rewards",
                sa.Column("expires_days", sa.Integer(), nullable=True),
            )

    if insp.has_table("reward_redemptions"):
        cols = {c["name"] for c in insp.get_columns("reward_redemptions")}
        if "discount_code" not in cols:
            op.add_column(
                "reward_redemptions",
                sa.Column("discount_code", sa.String(length=64), nullable=True),
            )
            op.create_index(
                "ix_reward_redemptions_discount_code",
                "reward_redemptions",
                ["discount_code"],
            )

    if not insp.has_table("loyalty_discount_entitlements"):
        op.create_table(
            "loyalty_discount_entitlements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("redemption_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("percent", sa.Integer(), nullable=False),
            sa.Column("min_purchase_toman", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_discount_toman", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("reserved_order_id", sa.Integer(), nullable=True),
            sa.Column("consumed_order_id", sa.Integer(), nullable=True),
            sa.Column("original_amount", sa.Integer(), nullable=True),
            sa.Column("discount_amount", sa.Integer(), nullable=True),
            sa.Column("final_amount", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["redemption_id"], ["reward_redemptions.id"]),
            sa.ForeignKeyConstraint(["reserved_order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["consumed_order_id"], ["orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_loyalty_discount_code"),
        )
        op.create_index(
            "ix_loyalty_discount_entitlements_user_id",
            "loyalty_discount_entitlements",
            ["user_id"],
        )
        op.create_index(
            "ix_loyalty_discount_entitlements_status",
            "loyalty_discount_entitlements",
            ["status"],
        )
        op.create_index(
            "ix_loyalty_discount_entitlements_code",
            "loyalty_discount_entitlements",
            ["code"],
        )
        op.create_index(
            "ix_loyalty_discount_entitlements_reserved_order_id",
            "loyalty_discount_entitlements",
            ["reserved_order_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("loyalty_discount_entitlements"):
        op.drop_table("loyalty_discount_entitlements")
    if insp.has_table("reward_redemptions"):
        cols = {c["name"] for c in insp.get_columns("reward_redemptions")}
        if "discount_code" in cols:
            op.drop_index("ix_reward_redemptions_discount_code", table_name="reward_redemptions")
            op.drop_column("reward_redemptions", "discount_code")
    if insp.has_table("loyalty_rewards"):
        cols = {c["name"] for c in insp.get_columns("loyalty_rewards")}
        for col in ("expires_days", "max_discount_toman", "min_purchase_toman"):
            if col in cols:
                op.drop_column("loyalty_rewards", col)
