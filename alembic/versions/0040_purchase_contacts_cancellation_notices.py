"""Shop contact verification and durable cancellation notification claims."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_contacts_cancel_notices"
down_revision = "0039_customer_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("service_cancellations")}
    if "notification_status" not in columns:
        op.add_column("service_cancellations", sa.Column(
            "notification_status", sa.String(24), nullable=False, server_default="pending",
        ))
        # Existing requests are already visible to staff; avoid a historical DM burst.
        bind.execute(sa.text("UPDATE service_cancellations SET notification_status = 'skipped'"))
    if "notification_attempted_at" not in columns:
        op.add_column("service_cancellations", sa.Column("notification_attempted_at", sa.DateTime(timezone=True)))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("service_cancellations")}
    if "ix_service_cancellations_notification" not in indexes:
        op.create_index("ix_service_cancellations_notification", "service_cancellations", ["notification_status", "id"])
    if "purchase_contacts" not in inspector.get_table_names():
        op.create_table("purchase_contacts",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("shop_key", sa.Integer(), primary_key=True),
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("phone_hash", sa.String(64), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    # Keep verified contacts for a later re-upgrade, including all existing rows.
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("service_cancellations")}
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("service_cancellations")}
    if "ix_service_cancellations_notification" in indexes:
        op.drop_index("ix_service_cancellations_notification", table_name="service_cancellations")
    with op.batch_alter_table("service_cancellations") as batch:
        for column in ("notification_attempted_at", "notification_status"):
            if column in columns:
                batch.drop_column(column)
