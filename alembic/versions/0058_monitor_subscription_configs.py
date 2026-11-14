"""Select native subscription configs while retaining legacy host selections.

Revision ID: 0058_monitor_subscription_configs
Revises: 0057_connection_status_menu
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0058_monitor_subscription_configs"
down_revision: str | None = "0057_connection_status_menu"
branch_labels: str | None = None
depends_on: str | None = None
TARGET = "connection_monitor_targets"
STATE = "connection_monitor_states"
MAIN_INDEX = "uq_monitor_target_main_config"
SHOP_INDEX = "uq_monitor_target_shop_config"


def _preserve_snapshots() -> bool:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite" or not sa.inspect(connection).has_table("connection_monitor_snapshots"):
        return False
    # SQLite batch rebuilds drop the parent table and can cascade into snapshots.
    connection.execute(sa.text("CREATE TEMPORARY TABLE _monitor_snapshot_rebuild AS SELECT * FROM connection_monitor_snapshots"))
    connection.execute(sa.text("DELETE FROM connection_monitor_snapshots"))
    return True


def _restore_snapshots() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("INSERT INTO connection_monitor_snapshots SELECT * FROM _monitor_snapshot_rebuild"))
    connection.execute(sa.text("DROP TABLE _monitor_snapshot_rebuild"))


def _pause_runtime() -> None:
    if sa.inspect(op.get_bind()).has_table(STATE):
        op.execute(sa.text("UPDATE connection_monitor_states SET enabled = false, cycle_token = NULL, cycle_lease_until = NULL, catalog_synced_at = NULL"))


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(TARGET):
        return
    columns = {column["name"]: column for column in inspector.get_columns(TARGET)}
    changed = "subscription_key" not in columns or "config_name" not in columns or not columns["pg_host_id"]["nullable"]
    if changed:
        saved = _preserve_snapshots()
        with op.batch_alter_table(TARGET) as batch:
            if "subscription_key" not in columns:
                batch.add_column(sa.Column("subscription_key", sa.String(64), nullable=True))
            if "config_name" not in columns:
                batch.add_column(sa.Column("config_name", sa.String(128), nullable=False, server_default=""))
            if not columns["pg_host_id"]["nullable"]:
                batch.alter_column("pg_host_id", existing_type=sa.Integer(), nullable=True)
        if saved:
            _restore_snapshots()
        _pause_runtime()
    op.execute(sa.text("UPDATE connection_monitor_targets SET test_enabled = false, is_public = false, generation = '', endpoint_count = 0, claim_token = NULL, claim_until = NULL, manual_pending = false WHERE subscription_key IS NULL"))
    indexes = {index["name"] for index in sa.inspect(connection).get_indexes(TARGET)}
    if MAIN_INDEX not in indexes:
        predicate = sa.text("reseller_id IS NULL AND subscription_key IS NOT NULL")
        op.create_index(MAIN_INDEX, TARGET, ["subscription_key"], unique=True, sqlite_where=predicate, postgresql_where=predicate)
    if SHOP_INDEX not in indexes:
        op.create_index(SHOP_INDEX, TARGET, ["reseller_id", "subscription_key"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(TARGET):
        return
    columns = {column["name"]: column for column in inspector.get_columns(TARGET)}
    if "subscription_key" not in columns:
        return
    _pause_runtime()
    op.execute(sa.text("UPDATE connection_monitor_targets SET test_enabled = false, is_public = false, claim_token = NULL, claim_until = NULL, generation = '', endpoint_count = 0, manual_pending = false WHERE subscription_key IS NOT NULL"))
    # Local negative identities retain new rows without impersonating panel hosts.
    op.execute(sa.text("UPDATE connection_monitor_targets SET pg_host_id = -id WHERE pg_host_id IS NULL"))
    indexes = {index["name"] for index in inspector.get_indexes(TARGET)}
    for name in (MAIN_INDEX, SHOP_INDEX):
        if name in indexes:
            op.drop_index(name, table_name=TARGET)
    saved = _preserve_snapshots()
    with op.batch_alter_table(TARGET) as batch:
        batch.alter_column("pg_host_id", existing_type=sa.Integer(), nullable=False)
        if "config_name" in columns:
            batch.drop_column("config_name")
        batch.drop_column("subscription_key")
    if saved:
        _restore_snapshots()
