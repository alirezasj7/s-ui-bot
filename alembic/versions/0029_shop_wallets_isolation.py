"""Per-shop wallet balances + topup tenancy columns.

Revision ID: 0029_shop_wallets_isolation
Revises: 0028_risk_color_tags_default_green

Root fix for shared global wallet minting: shop-sourced credits land in
``shop_wallets`` (user_id, reseller_id) and can only be spent on that shop's
orders. Platform ``bot_users.wallet_balance`` stays the main-bot / PAYG purse.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0029_shop_wallets_isolation"
down_revision: str = "0028_risk_color_tags_default_green"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "shop_wallets" not in tables:
        op.create_table(
            "shop_wallets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=False),
            sa.Column(
                "reseller_id",
                sa.Integer(),
                sa.ForeignKey("bot_users.id"),
                nullable=False,
            ),
            sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id", "reseller_id", name="uq_shop_wallets_user_reseller"
            ),
        )
        op.create_index("ix_shop_wallets_user_id", "shop_wallets", ["user_id"])
        op.create_index("ix_shop_wallets_reseller_id", "shop_wallets", ["reseller_id"])

    wt_cols = {c["name"] for c in insp.get_columns("wallet_transactions")}
    if "reseller_id" not in wt_cols:
        op.add_column(
            "wallet_transactions",
            sa.Column(
                "reseller_id",
                sa.Integer(),
                sa.ForeignKey("bot_users.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_wallet_transactions_reseller_id",
            "wallet_transactions",
            ["reseller_id"],
        )

    pay_cols = {c["name"] for c in insp.get_columns("payments")}
    if "wallet_shop_id" not in pay_cols:
        op.add_column(
            "payments",
            sa.Column(
                "wallet_shop_id",
                sa.Integer(),
                sa.ForeignKey("bot_users.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_payments_wallet_shop_id",
            "payments",
            ["wallet_shop_id"],
        )

    # Refresh inspector after possible adds above
    insp = sa.inspect(conn)
    loy_cols = {c["name"] for c in insp.get_columns("loyalty_discount_entitlements")}
    if "reseller_id" not in loy_cols:
        op.add_column(
            "loyalty_discount_entitlements",
            sa.Column(
                "reseller_id",
                sa.Integer(),
                sa.ForeignKey("bot_users.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_loyalty_discount_entitlements_reseller_id",
            "loyalty_discount_entitlements",
            ["reseller_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "loyalty_discount_entitlements" in tables:
        cols = {c["name"] for c in insp.get_columns("loyalty_discount_entitlements")}
        if "reseller_id" in cols:
            op.drop_index(
                "ix_loyalty_discount_entitlements_reseller_id",
                table_name="loyalty_discount_entitlements",
            )
            op.drop_column("loyalty_discount_entitlements", "reseller_id")

    if "payments" in tables:
        cols = {c["name"] for c in insp.get_columns("payments")}
        if "wallet_shop_id" in cols:
            op.drop_index("ix_payments_wallet_shop_id", table_name="payments")
            op.drop_column("payments", "wallet_shop_id")

    if "wallet_transactions" in tables:
        cols = {c["name"] for c in insp.get_columns("wallet_transactions")}
        if "reseller_id" in cols:
            op.drop_index(
                "ix_wallet_transactions_reseller_id",
                table_name="wallet_transactions",
            )
            op.drop_column("wallet_transactions", "reseller_id")

    if "shop_wallets" in tables:
        op.drop_index("ix_shop_wallets_reseller_id", table_name="shop_wallets")
        op.drop_index("ix_shop_wallets_user_id", table_name="shop_wallets")
        op.drop_table("shop_wallets")
