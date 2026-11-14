"""Connection support, service cancellations and targeted campaigns."""
import sqlalchemy as sa
from alembic import op

revision = "0039_customer_features"
down_revision = "0038_renewal_preview"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("user_services")}
    for name in ("cancellation_pending", "is_cancelled"):
        if name not in columns:
            op.add_column("user_services", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    if "quota_status" not in columns:
        op.add_column("user_services", sa.Column("quota_status", sa.String(32), nullable=True))
    tables = set(sa.inspect(bind).get_table_names())
    if "service_cancellations" not in tables:
        op.create_table("service_cancellations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("user_services.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reseller_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE")),
            sa.Column("reason", sa.Text(), nullable=False), sa.Column("pg_user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("refund_amount", sa.BigInteger()),
            sa.Column("operator_note", sa.Text(), nullable=False), sa.Column("processed_by", sa.String(128)),
            sa.Column("lock_token", sa.String(32)), sa.Column("locked_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime(timezone=True)))
        for col in ("service_id", "user_id", "reseller_id", "status"):
            op.create_index(f"ix_service_cancellations_{col}", "service_cancellations", [col])
        op.create_index("uq_service_cancellations_open", "service_cancellations", ["service_id"], unique=True,
            sqlite_where=sa.text("status IN ('pending','processing','review','approved')"),
            postgresql_where=sa.text("status IN ('pending','processing','review','approved')"))
    if "targeted_campaigns" not in tables:
        op.create_table("targeted_campaigns", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reseller_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE")),
            sa.Column("audience", sa.String(24), nullable=False), sa.Column("days", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False), sa.Column("status", sa.String(24), nullable=False),
            sa.Column("created_by", sa.String(128), nullable=False), sa.Column("lock_token", sa.String(32)),
            sa.Column("locked_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
        for col in ("reseller_id", "status"):
            op.create_index(f"ix_targeted_campaigns_{col}", "targeted_campaigns", [col])
    if "campaign_recipients" not in tables:
        op.create_table("campaign_recipients", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("targeted_campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("message_id", sa.Integer()),
            sa.Column("attempted_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("campaign_id", "user_id", name="uq_campaign_recipient"))
        for col in ("campaign_id", "user_id", "status"):
            op.create_index(f"ix_campaign_recipients_{col}", "campaign_recipients", [col])
    if "marketing_preferences" not in tables:
        op.create_table("marketing_preferences",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("shop_key", sa.Integer(), primary_key=True), sa.Column("enabled", sa.Boolean(), nullable=False))


def downgrade():
    for table in ("marketing_preferences", "campaign_recipients", "targeted_campaigns", "service_cancellations"):
        op.drop_table(table)
    op.drop_column("user_services", "is_cancelled")
    op.drop_column("user_services", "cancellation_pending")
    op.drop_column("user_services", "quota_status")
