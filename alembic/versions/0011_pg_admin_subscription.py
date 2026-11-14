"""Alembic revision: PG admin subscription clock + reseller plan kinds.

Revision ID: 0011_pg_admin_subscription
Revises: 0010_bot_users_reseller_id_index
Create Date: 2026-08-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_pg_admin_subscription"
down_revision: Union[str, None] = "0010_bot_users_reseller_id_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        adds = [
            ("plan_kind", sa.Column("plan_kind", sa.String(32), server_default="subscription", nullable=False)),
            ("duration_days", sa.Column("duration_days", sa.Integer(), server_default="0", nullable=False)),
            ("included_gb", sa.Column("included_gb", sa.Integer(), server_default="0", nullable=False)),
            ("included_users", sa.Column("included_users", sa.Integer(), server_default="0", nullable=False)),
            ("addon_gb", sa.Column("addon_gb", sa.Integer(), server_default="0", nullable=False)),
            ("addon_users", sa.Column("addon_users", sa.Integer(), server_default="0", nullable=False)),
            (
                "renew_pricing_mode",
                sa.Column("renew_pricing_mode", sa.String(32), server_default="fixed", nullable=False),
            ),
        ]
        for name, col in adds:
            if name not in cols:
                op.add_column("reseller_plans", col)

    if not insp.has_table("pg_admin_subscriptions"):
        op.create_table(
            "pg_admin_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("pg_username", sa.String(128), nullable=False),
            sa.Column("plan_id", sa.Integer(), sa.ForeignKey("reseller_plans.id"), nullable=True),
            sa.Column("access_status", sa.String(16), server_default="active", nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("base_gb", sa.Integer(), server_default="0", nullable=False),
            sa.Column("base_users", sa.Integer(), server_default="0", nullable=False),
            sa.Column("extra_gb_purchased", sa.Integer(), server_default="0", nullable=False),
            sa.Column("extra_users_purchased", sa.Integer(), server_default="0", nullable=False),
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expiry_disabled_user_ids", sa.Text(), nullable=True),
            sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("renew_generation", sa.Integer(), server_default="0", nullable=False),
            sa.Column("warn_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_pg_admin_subscriptions_pg_username", "pg_admin_subscriptions", ["pg_username"], unique=True)
        op.create_index("ix_pg_admin_subscriptions_plan_id", "pg_admin_subscriptions", ["plan_id"])
        op.create_index("ix_pg_admin_subscriptions_access_status", "pg_admin_subscriptions", ["access_status"])
        op.create_index("ix_pg_admin_subscriptions_expires_at", "pg_admin_subscriptions", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("pg_admin_subscriptions"):
        op.drop_table("pg_admin_subscriptions")
    if insp.has_table("reseller_plans"):
        cols = {c["name"] for c in insp.get_columns("reseller_plans")}
        for col in (
            "renew_pricing_mode",
            "addon_users",
            "addon_gb",
            "included_users",
            "included_gb",
            "duration_days",
            "plan_kind",
        ):
            if col in cols:
                op.drop_column("reseller_plans", col)
