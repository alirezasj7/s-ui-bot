"""Per-service automatic wallet renewal and quota packs."""

import sqlalchemy as sa
from alembic import op

revision = "0034_service_automations"
down_revision = "0033_plan_category_button_style"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("service_automations"):
        return
    op.create_table(
        "service_automations",
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("user_services.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "shop_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=True
        ),
        sa.Column(
            "renew_plan_id",
            sa.Integer(),
            sa.ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "duration_pack_id",
            sa.Integer(),
            sa.ForeignKey("service_addon_packs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "volume_pack_id",
            sa.Integer(),
            sa.ForeignKey("service_addon_packs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *[
            sa.Column(
                f"{action}_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
            for action in ("renew", "duration", "volume")
        ],
        *[
            sa.Column(f"{action}_notice", sa.String(32), nullable=True)
            for action in ("renew", "duration", "volume")
        ],
        sa.Column(
            "pending_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True
        ),
        sa.Column("pending_action", sa.String(16), nullable=True),
        sa.Column(
            "needs_review", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("lock_token", sa.String(32), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("service_automations"):
        op.drop_table("service_automations")
