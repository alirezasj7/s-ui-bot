"""Renewal terms, durable targets and per-service delivery exclusion."""

import sqlalchemy as sa
from alembic import op

revision = "0038_renewal_preview"
down_revision = "0037_gift_code_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("orders")}
    if "renewal_snapshot" not in columns:
        op.add_column("orders", sa.Column("renewal_snapshot", sa.Text(), nullable=True))
    if "renewal_request_key" not in columns:
        op.add_column("orders", sa.Column("renewal_request_key", sa.String(64), nullable=True))
    if "service_mutation_pending" not in columns:
        op.add_column("orders", sa.Column("service_mutation_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "uq_orders_service_quota_mutation" not in {
        i["name"] for i in sa.inspect(op.get_bind()).get_indexes("orders")
    }:
        op.create_index(
            "uq_orders_service_quota_mutation", "orders", ["service_id"], unique=True,
            sqlite_where=sa.text("service_mutation_pending = true"),
            postgresql_where=sa.text("service_mutation_pending = true"),
        )
    if "uq_orders_renewal_request_key" not in {
        i["name"] for i in sa.inspect(op.get_bind()).get_indexes("orders")
    }:
        op.create_index("uq_orders_renewal_request_key", "orders", ["renewal_request_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_orders_service_quota_mutation", table_name="orders")
    op.drop_index("uq_orders_renewal_request_key", table_name="orders")
    op.drop_column("orders", "service_mutation_pending")
    op.drop_column("orders", "renewal_snapshot")
    op.drop_column("orders", "renewal_request_key")
