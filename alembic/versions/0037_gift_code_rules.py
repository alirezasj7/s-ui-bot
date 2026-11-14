"""Gift code expiry, capped discounts, purchase rules and per-user usage.

Revision ID: 0037_gift_code_rules
Revises: 0036_limits_guides_receipts
"""

from alembic import op

revision = "0037_gift_code_rules"
down_revision = "0036_limits_guides_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.gift_codes_schema import upgrade_gift_codes

    upgrade_gift_codes(op.get_bind())


def downgrade() -> None:
    op.drop_table("charge_code_uses")
    for name in (
        "purchase_types",
        "first_purchase_only",
        "max_uses_per_user",
        "expires_at",
        "max_discount_toman",
        "percent",
        "kind",
    ):
        op.drop_column("charge_codes", name)
