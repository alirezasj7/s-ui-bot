"""Referral + Loyalty / Points tables and BotUser.points_balance.

Revision ID: 0007_referral_loyalty
Revises: 0006_payg_wallet_linked
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_referral_loyalty"
down_revision: Union[str, None] = "0006_payg_wallet_linked"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("bot_users"):
        cols = {c["name"] for c in insp.get_columns("bot_users")}
        if "points_balance" not in cols:
            op.add_column(
                "bot_users",
                sa.Column("points_balance", sa.Integer(), server_default="0", nullable=False),
            )

    if not insp.has_table("points_transactions"):
        op.create_table(
            "points_transactions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("tx_type", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("reference", sa.String(length=128), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column("reversed_tx_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["reversed_tx_id"], ["points_transactions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_points_tx_idempotency"),
        )
        op.create_index("ix_points_transactions_user_id", "points_transactions", ["user_id"])
        op.create_index("ix_points_transactions_tx_type", "points_transactions", ["tx_type"])
        op.create_index("ix_points_transactions_source", "points_transactions", ["source"])
        op.create_index("ix_points_transactions_reference", "points_transactions", ["reference"])

    if not insp.has_table("points_rules"):
        op.create_table(
            "points_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("event_key", sa.String(length=64), nullable=False),
            sa.Column("amount_mode", sa.String(length=32), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("first_time_only", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("min_purchase_toman", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_purchase_gb", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_reward", sa.Integer(), nullable=True),
            sa.Column("cooldown_hours", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("plan_id", sa.Integer(), nullable=True),
            sa.Column("tier_min_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_points_rules_event_key", "points_rules", ["event_key"])
        op.create_index("ix_points_rules_reseller_id", "points_rules", ["reseller_id"])

    if not insp.has_table("loyalty_rewards"):
        op.create_table(
            "loyalty_rewards",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("reward_type", sa.String(length=32), nullable=False),
            sa.Column("reward_value", sa.Integer(), nullable=False),
            sa.Column("points_cost", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("max_redemptions_global", sa.Integer(), nullable=True),
            sa.Column("max_redemptions_per_user", sa.Integer(), nullable=True),
            sa.Column("redemption_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_loyalty_rewards_reward_type", "loyalty_rewards", ["reward_type"])
        op.create_index("ix_loyalty_rewards_reseller_id", "loyalty_rewards", ["reseller_id"])

    if not insp.has_table("reward_redemptions"):
        op.create_table(
            "reward_redemptions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("reward_id", sa.Integer(), nullable=False),
            sa.Column("points_spent", sa.Integer(), nullable=False),
            sa.Column("reward_type", sa.String(length=32), nullable=False),
            sa.Column("reward_value", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("service_id", sa.Integer(), nullable=True),
            sa.Column("points_tx_id", sa.Integer(), nullable=True),
            sa.Column("wallet_reason", sa.String(length=255), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["reward_id"], ["loyalty_rewards.id"]),
            sa.ForeignKeyConstraint(["service_id"], ["user_services.id"]),
            sa.ForeignKeyConstraint(["points_tx_id"], ["points_transactions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_reward_redemption_idempotency"),
        )
        op.create_index("ix_reward_redemptions_user_id", "reward_redemptions", ["user_id"])
        op.create_index("ix_reward_redemptions_reward_id", "reward_redemptions", ["reward_id"])
        op.create_index("ix_reward_redemptions_status", "reward_redemptions", ["status"])

    if not insp.has_table("referral_events"):
        op.create_table(
            "referral_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("referrer_id", sa.Integer(), nullable=False),
            sa.Column("referred_id", sa.Integer(), nullable=False),
            sa.Column("event_key", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("qualification_state", sa.String(length=32), nullable=False),
            sa.Column("reward_state", sa.String(length=32), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["referrer_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["referred_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_referral_event_idempotency"),
        )
        op.create_index("ix_referral_events_referrer_id", "referral_events", ["referrer_id"])
        op.create_index("ix_referral_events_referred_id", "referral_events", ["referred_id"])
        op.create_index("ix_referral_events_event_key", "referral_events", ["event_key"])

    if not insp.has_table("loyalty_tiers"):
        op.create_table(
            "loyalty_tiers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("min_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_points", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("multiplier_bps", sa.Integer(), nullable=False, server_default="10000"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in (
        "reward_redemptions",
        "loyalty_rewards",
        "referral_events",
        "points_rules",
        "points_transactions",
        "loyalty_tiers",
    ):
        if insp.has_table(table):
            op.drop_table(table)
    if insp.has_table("bot_users"):
        cols = {c["name"] for c in insp.get_columns("bot_users")}
        if "points_balance" in cols:
            op.drop_column("bot_users", "points_balance")
