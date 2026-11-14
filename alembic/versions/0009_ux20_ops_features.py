"""UX20 ops features: delivery failures, charge codes, funnel, notes, risk.

Revision ID: 0009_ux20_ops_features
Revises: 0008_loyalty_discounts
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_ux20_ops_features"
down_revision: Union[str, None] = "0008_loyalty_discounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_col(insp, table: str, name: str, col) -> None:
    if not insp.has_table(table):
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if name not in cols:
        op.add_column(table, col)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    _add_col(insp, "bot_users", "staff_note", sa.Column("staff_note", sa.Text(), nullable=True))
    _add_col(
        insp,
        "bot_users",
        "risk_flags",
        sa.Column("risk_flags", sa.String(length=255), nullable=True),
    )
    _add_col(insp, "orders", "staff_note", sa.Column("staff_note", sa.Text(), nullable=True))
    _add_col(
        insp,
        "user_services",
        "renew_nudge_sent_at",
        sa.Column("renew_nudge_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_col(
        insp,
        "reseller_profiles",
        "capacity_warned_at",
        sa.Column("capacity_warned_at", sa.DateTime(timezone=True), nullable=True),
    )

    if not insp.has_table("delivery_failures"):
        op.create_table(
            "delivery_failures",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("payment_id", sa.Integer(), nullable=True),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "last_attempt_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_delivery_failures_order_id", "delivery_failures", ["order_id"])
        op.create_index("ix_delivery_failures_reseller_id", "delivery_failures", ["reseller_id"])

    if not insp.has_table("charge_codes"):
        op.create_table(
            "charge_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
        op.create_index("ix_charge_codes_code", "charge_codes", ["code"])
        op.create_index("ix_charge_codes_reseller_id", "charge_codes", ["reseller_id"])

    if not insp.has_table("funnel_events"):
        op.create_table(
            "funnel_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("reseller_id", sa.Integer(), nullable=True),
            sa.Column("step", sa.String(length=64), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=True),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["reseller_id"], ["bot_users.id"]),
            sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_funnel_events_idem"),
        )
        op.create_index("ix_funnel_events_user_id", "funnel_events", ["user_id"])
        op.create_index("ix_funnel_events_reseller_id", "funnel_events", ["reseller_id"])
        op.create_index("ix_funnel_events_step", "funnel_events", ["step"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("funnel_events", "charge_codes", "delivery_failures"):
        if insp.has_table(table):
            op.drop_table(table)
    for table, col in (
        ("reseller_profiles", "capacity_warned_at"),
        ("user_services", "renew_nudge_sent_at"),
        ("orders", "staff_note"),
        ("bot_users", "risk_flags"),
        ("bot_users", "staff_note"),
    ):
        if insp.has_table(table):
            cols = {c["name"] for c in insp.get_columns(table)}
            if col in cols:
                op.drop_column(table, col)
