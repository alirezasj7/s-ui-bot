"""Remember all staff copies of payment review messages."""

import sqlalchemy as sa
from alembic import op

revision = "0035_payment_review_messages"
down_revision = "0034_service_automations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("payment_review_messages"):
        return
    op.create_table(
        "payment_review_messages",
        sa.Column("bot_id", sa.BigInteger(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("message_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "payment_id", sa.Integer(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_photo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_payment_review_messages_payment_id", "payment_review_messages", ["payment_id"]
    )


def downgrade() -> None:
    op.drop_table("payment_review_messages")
