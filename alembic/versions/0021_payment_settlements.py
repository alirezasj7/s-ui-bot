"""Payment settlements table — additive PSP / card-auto ledger.

Revision ID: 0021_payment_settlements
Revises: 0020_inbox_dismissals
Create Date: 2026-08-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_payment_settlements"
down_revision: Union[str, None] = "0020_inbox_dismissals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("payment_settlements"):
        # Safe re-run on DBs that got an earlier draft of this revision.
        cols = {c["name"] for c in insp.get_columns("payment_settlements")}
        if "tenant_key" not in cols:
            op.add_column(
                "payment_settlements",
                sa.Column("tenant_key", sa.Integer(), nullable=False, server_default="0"),
            )
        existing_ix = {i["name"] for i in insp.get_indexes("payment_settlements")}
        if "uq_payment_settlements_active_payment_channel" not in existing_ix:
            op.create_index(
                "uq_payment_settlements_active_payment_channel",
                "payment_settlements",
                ["payment_id", "channel"],
                unique=True,
                sqlite_where=sa.text("status IN ('created','awaiting','settling')"),
                postgresql_where=sa.text("status IN ('created','awaiting','settling')"),
            )
        if "uq_payment_settlements_tenant_ext_ref" not in existing_ix:
            op.create_index(
                "uq_payment_settlements_tenant_ext_ref",
                "payment_settlements",
                ["channel", "provider", "tenant_key", "external_ref"],
                unique=True,
                sqlite_where=sa.text(
                    "external_ref IS NOT NULL AND status IN ('settling','settled')"
                ),
                postgresql_where=sa.text(
                    "external_ref IS NOT NULL AND status IN ('settling','settled')"
                ),
            )
        return

    op.create_table(
        "payment_settlements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("shop_owner_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=True),
        sa.Column("tenant_key", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IRT"),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("external_ref", sa.String(128), nullable=True),
        sa.Column("checkout_token", sa.String(64), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("provider_payload", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_settlements_idempotency"),
    )
    op.create_index("ix_payment_settlements_payment_id", "payment_settlements", ["payment_id"])
    op.create_index("ix_payment_settlements_shop_owner_id", "payment_settlements", ["shop_owner_id"])
    op.create_index("ix_payment_settlements_tenant_key", "payment_settlements", ["tenant_key"])
    op.create_index("ix_payment_settlements_channel", "payment_settlements", ["channel"])
    op.create_index("ix_payment_settlements_provider", "payment_settlements", ["provider"])
    op.create_index("ix_payment_settlements_status", "payment_settlements", ["status"])
    op.create_index(
        "ix_payment_settlements_external_ref",
        "payment_settlements",
        ["provider", "external_ref"],
    )
    op.create_index(
        "uq_payment_settlements_active_payment_channel",
        "payment_settlements",
        ["payment_id", "channel"],
        unique=True,
        sqlite_where=sa.text("status IN ('created','awaiting','settling')"),
        postgresql_where=sa.text("status IN ('created','awaiting','settling')"),
    )
    op.create_index(
        "uq_payment_settlements_tenant_ext_ref",
        "payment_settlements",
        ["channel", "provider", "tenant_key", "external_ref"],
        unique=True,
        sqlite_where=sa.text(
            "external_ref IS NOT NULL AND status IN ('settling','settled')"
        ),
        postgresql_where=sa.text(
            "external_ref IS NOT NULL AND status IN ('settling','settled')"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("payment_settlements"):
        return
    for name in (
        "uq_payment_settlements_tenant_ext_ref",
        "uq_payment_settlements_active_payment_channel",
        "ix_payment_settlements_external_ref",
        "ix_payment_settlements_status",
        "ix_payment_settlements_provider",
        "ix_payment_settlements_channel",
        "ix_payment_settlements_tenant_key",
        "ix_payment_settlements_shop_owner_id",
        "ix_payment_settlements_payment_id",
    ):
        try:
            op.drop_index(name, table_name="payment_settlements")
        except Exception:
            pass
    op.drop_table("payment_settlements")
