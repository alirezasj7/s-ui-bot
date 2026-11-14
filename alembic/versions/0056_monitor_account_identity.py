"""Exclude legacy customer accounts with only a panel username from monitoring.

Revision ID: 0056_monitor_account_identity
Revises: 0055_connection_monitor
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0056_monitor_account_identity"
down_revision: str | None = "0055_connection_monitor"
branch_labels: str | None = None
depends_on: str | None = None
STATE = "connection_monitor_states"
INDEX = "ix_user_services_pg_username_lower"


def _has_index() -> bool:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table("user_services"):
        return False
    if connection.dialect.name == "sqlite":
        # SQLAlchemy cannot reflect SQLite expression indexes; this fixed table
        # pragma includes them and keeps repeated upgrades/downgrades idempotent.
        return any(row._mapping["name"] == INDEX for row in connection.execute(sa.text("PRAGMA index_list('user_services')")))
    return any(index["name"] == INDEX for index in sa.inspect(connection).get_indexes("user_services"))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(STATE) and "pg_username" not in {column["name"] for column in inspector.get_columns(STATE)}:
        with op.batch_alter_table(STATE) as batch:
            batch.add_column(sa.Column("pg_username", sa.String(128), nullable=True))
        # Earlier draft settings do not prove the account's legacy username.
        # Require explicit reattachment; never guess identity from a token.
        op.execute(sa.text("UPDATE connection_monitor_states SET enabled = false, cycle_token = NULL, cycle_lease_until = NULL, catalog_synced_at = NULL"))
        if inspector.has_table("connection_monitor_targets"):
            op.execute(sa.text("UPDATE connection_monitor_targets SET is_public = false, claim_token = NULL, claim_until = NULL"))
    if inspector.has_table("user_services") and not _has_index():
        op.create_index(INDEX, "user_services", [sa.text("lower(pg_username)")])


def downgrade() -> None:
    if _has_index():
        op.drop_index(INDEX, table_name="user_services")
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(STATE) and "pg_username" in {column["name"] for column in inspector.get_columns(STATE)}:
        with op.batch_alter_table(STATE) as batch:
            batch.drop_column("pg_username")
