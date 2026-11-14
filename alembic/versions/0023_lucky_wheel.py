"""Lucky wheel prizes, spins ledger, and user state.

Revision ID: 0023_lucky_wheel
Revises: 0022_drop_reseller_commission
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_lucky_wheel"
down_revision: Union[str, None] = "0022_drop_reseller_commission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("lucky_wheel_prizes"):
        op.create_table(
            "lucky_wheel_prizes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("prize_type", sa.String(length=32), nullable=False),
            sa.Column("prize_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("max_wins_global", sa.Integer(), nullable=True),
            sa.Column("max_wins_per_user", sa.Integer(), nullable=True),
            sa.Column("win_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_purchase_toman", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_discount_toman", sa.Integer(), nullable=True),
            sa.Column("expires_days", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_lucky_wheel_prizes_reseller_id", "lucky_wheel_prizes", ["reseller_id"])
        op.create_index("ix_lucky_wheel_prizes_prize_type", "lucky_wheel_prizes", ["prize_type"])

    if not insp.has_table("lucky_wheel_spins"):
        op.create_table(
            "lucky_wheel_spins",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("prize_id", sa.Integer(), nullable=True),
            sa.Column("prize_type", sa.String(length=32), nullable=False, server_default="none"),
            sa.Column("prize_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "prize_label_snapshot", sa.String(length=128), nullable=False, server_default=""
            ),
            sa.Column("cost_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_free_spin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
            sa.Column("points_tx_id", sa.Integer(), nullable=True),
            sa.Column("service_id", sa.Integer(), nullable=True),
            sa.Column("discount_code", sa.String(length=64), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["prize_id"], ["lucky_wheel_prizes.id"]),
            sa.ForeignKeyConstraint(["points_tx_id"], ["points_transactions.id"]),
            sa.ForeignKeyConstraint(["service_id"], ["user_services.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_lucky_wheel_spin_idempotency"),
        )
        op.create_index("ix_lucky_wheel_spins_user_id", "lucky_wheel_spins", ["user_id"])
        op.create_index("ix_lucky_wheel_spins_reseller_id", "lucky_wheel_spins", ["reseller_id"])
        op.create_index("ix_lucky_wheel_spins_prize_id", "lucky_wheel_spins", ["prize_id"])
        op.create_index("ix_lucky_wheel_spins_status", "lucky_wheel_spins", ["status"])

    if not insp.has_table("lucky_wheel_user_state"):
        op.create_table(
            "lucky_wheel_user_state",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("free_spins_balance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_spin_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("spins_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("spins_day", sa.String(length=10), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_lucky_wheel_user_state_user"),
        )
        op.create_index("ix_lucky_wheel_user_state_user_id", "lucky_wheel_user_state", ["user_id"])
        op.create_index(
            "ix_lucky_wheel_user_state_reseller_id", "lucky_wheel_user_state", ["reseller_id"]
        )

    if insp.has_table("loyalty_discount_entitlements"):
        cols = {c["name"] for c in insp.get_columns("loyalty_discount_entitlements")}
        if "wheel_spin_id" not in cols:
            op.add_column(
                "loyalty_discount_entitlements",
                sa.Column("wheel_spin_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_loyalty_discount_entitlements_wheel_spin_id",
                "loyalty_discount_entitlements",
                ["wheel_spin_id"],
            )
            op.create_foreign_key(
                "fk_loyalty_discount_entitlements_wheel_spin_id",
                "loyalty_discount_entitlements",
                "lucky_wheel_spins",
                ["wheel_spin_id"],
                ["id"],
            )
        try:
            with op.batch_alter_table("loyalty_discount_entitlements") as batch:
                batch.alter_column(
                    "redemption_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("loyalty_discount_entitlements"):
        cols = {c["name"] for c in insp.get_columns("loyalty_discount_entitlements")}
        if "wheel_spin_id" in cols:
            try:
                op.drop_constraint(
                    "fk_loyalty_discount_entitlements_wheel_spin_id",
                    "loyalty_discount_entitlements",
                    type_="foreignkey",
                )
            except Exception:
                pass
            try:
                op.drop_index(
                    "ix_loyalty_discount_entitlements_wheel_spin_id",
                    table_name="loyalty_discount_entitlements",
                )
            except Exception:
                pass
            op.drop_column("loyalty_discount_entitlements", "wheel_spin_id")

    if insp.has_table("lucky_wheel_user_state"):
        op.drop_table("lucky_wheel_user_state")
    if insp.has_table("lucky_wheel_spins"):
        op.drop_table("lucky_wheel_spins")
    if insp.has_table("lucky_wheel_prizes"):
        op.drop_table("lucky_wheel_prizes")
