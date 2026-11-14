"""Limits/guides ops: redemptions, trial phone hash, receipt fingerprints.

Revision ID: 0036_limits_guides_receipts
Revises: 0035_payment_review_messages
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_limits_guides_receipts"
down_revision: Union[str, None] = "0035_payment_review_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("trial_claims"):
        op.create_table(
            "trial_claims",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=False),
            sa.Column("shop_key", sa.String(length=64), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("phone_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("user_id", "shop_key", name="uq_trial_claims_user_shop"),
            sa.UniqueConstraint("telegram_id", "shop_key", name="uq_trial_claims_tg_shop"),
            sa.UniqueConstraint("phone_hash", "shop_key", name="uq_trial_claims_phone_shop"),
        )
        op.create_index("ix_trial_claims_user_id", "trial_claims", ["user_id"])
    else:
        cols = {c["name"] for c in insp.get_columns("trial_claims")}
        if "telegram_id" not in cols:
            op.add_column("trial_claims", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
        if "phone_hash" not in cols:
            op.add_column(
                "trial_claims", sa.Column("phone_hash", sa.String(length=64), nullable=True)
            )
        uqs = {uq.get("name") for uq in insp.get_unique_constraints("trial_claims")}
        if "uq_trial_claims_tg_shop" not in uqs:
            op.create_unique_constraint(
                "uq_trial_claims_tg_shop", "trial_claims", ["telegram_id", "shop_key"]
            )
        if "uq_trial_claims_phone_shop" not in uqs:
            op.create_unique_constraint(
                "uq_trial_claims_phone_shop", "trial_claims", ["phone_hash", "shop_key"]
            )

    if not insp.has_table("charge_code_redemptions"):
        op.create_table(
            "charge_code_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "code_id",
                sa.Integer(),
                sa.ForeignKey("charge_codes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("bot_users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("code_id", "user_id", name="uq_charge_code_redemptions_code_user"),
        )
        op.create_index("ix_charge_code_redemptions_code_id", "charge_code_redemptions", ["code_id"])
        op.create_index("ix_charge_code_redemptions_user_id", "charge_code_redemptions", ["user_id"])

    if not insp.has_table("payment_receipt_fingerprints"):
        op.create_table(
            "payment_receipt_fingerprints",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "payment_id",
                sa.Integer(),
                sa.ForeignKey("payments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("file_unique_id", sa.String(length=128), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_payment_receipt_fingerprints_payment_id",
            "payment_receipt_fingerprints",
            ["payment_id"],
        )
        op.create_index(
            "ix_payment_receipt_fingerprints_file_unique_id",
            "payment_receipt_fingerprints",
            ["file_unique_id"],
        )
        op.create_index(
            "ix_payment_receipt_fingerprints_sha256",
            "payment_receipt_fingerprints",
            ["sha256"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("payment_receipt_fingerprints"):
        op.drop_table("payment_receipt_fingerprints")
    if insp.has_table("charge_code_redemptions"):
        op.drop_table("charge_code_redemptions")
    if insp.has_table("trial_claims"):
        cols = {c["name"] for c in insp.get_columns("trial_claims")}
        uqs = {uq.get("name") for uq in insp.get_unique_constraints("trial_claims")}
        if "uq_trial_claims_phone_shop" in uqs:
            op.drop_constraint("uq_trial_claims_phone_shop", "trial_claims", type_="unique")
        if "uq_trial_claims_tg_shop" in uqs:
            op.drop_constraint("uq_trial_claims_tg_shop", "trial_claims", type_="unique")
        if "phone_hash" in cols:
            op.drop_column("trial_claims", "phone_hash")
        if "telegram_id" in cols:
            op.drop_column("trial_claims", "telegram_id")
