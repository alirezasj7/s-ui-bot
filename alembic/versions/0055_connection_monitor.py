"""Persist selected-host monitoring without enabling probes or publication.

Revision ID: 0055_connection_monitor
Revises: 0054_panel_alert_states
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0055_connection_monitor"
down_revision: str | None = "0054_panel_alert_states"
branch_labels: str | None = None
depends_on: str | None = None

STATE = "connection_monitor_states"
TARGET = "connection_monitor_targets"
SNAPSHOT = "connection_monitor_snapshots"


def _scope_column() -> sa.Column:
    return sa.Column("reseller_id", sa.Integer(), sa.ForeignKey("bot_users.id"), nullable=True)


def _time_column(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _create_state() -> None:
    op.create_table(
        STATE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _scope_column(),
        sa.Column("probe_id", sa.String(16), nullable=False, server_default="local"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pg_user_id", sa.Integer(), nullable=True),
        sa.Column("subscription_token_enc", sa.Text(), nullable=True),
        sa.Column("account_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("cycle_token", sa.String(64), nullable=True),
        _time_column("cycle_lease_until"),
        _time_column("catalog_synced_at"),
        sa.UniqueConstraint("reseller_id", "probe_id", name="uq_monitor_state_shop_probe"),
    )


def _create_target() -> None:
    op.create_table(
        TARGET,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _scope_column(),
        sa.Column("pg_host_id", sa.Integer(), nullable=False),
        sa.Column("test_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("public_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation", sa.String(64), nullable=False, server_default=""),
        sa.Column("endpoint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claim_token", sa.String(64), nullable=True),
        _time_column("claim_until"),
        _time_column("manual_available_at"),
        sa.Column("manual_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("reseller_id", "pg_host_id", name="uq_monitor_target_shop_host"),
        sa.CheckConstraint("display_order >= 0 AND display_order <= 2147483647", name="ck_monitor_target_order"),
        sa.CheckConstraint("endpoint_count >= 0 AND endpoint_count <= 12", name="ck_monitor_target_endpoints"),
        sa.CheckConstraint("NOT is_public OR (test_enabled AND length(trim(public_name)) > 0)", name="ck_monitor_target_public"),
    )


def _create_snapshot() -> None:
    op.create_table(
        SNAPSHOT,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _scope_column(),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey(f"{TARGET}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_key", sa.String(64), nullable=False),
        sa.Column("probe_id", sa.String(16), nullable=False, server_default="local"),
        sa.Column("generation", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("reason", sa.String(32), nullable=True),
        _time_column("checked_at"),
        sa.Column("destination", sa.String(32), nullable=True),
        sa.Column("delay_ms", sa.Integer(), nullable=True),
        sa.Column("success_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_observation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recovery_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("samples_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("target_id", "endpoint_key", "probe_id", name="uq_monitor_snapshot_endpoint"),
        sa.CheckConstraint("delay_ms IS NULL OR delay_ms >= 0", name="ck_monitor_snapshot_delay"),
        sa.CheckConstraint("success_streak >= 0 AND failure_streak >= 0", name="ck_monitor_snapshot_streaks"),
        sa.CheckConstraint("status IN ('healthy', 'degraded', 'down', 'unknown', 'not_ready', 'paused')", name="ck_monitor_snapshot_status"),
    )


def _ensure_index(table: str, name: str, columns: list[str], *, main_only: bool = False) -> None:
    if name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        return
    if main_only:
        predicate = sa.text("reseller_id IS NULL")
        op.create_index(name, table, columns, unique=True, sqlite_where=predicate, postgresql_where=predicate)
    else:
        op.create_index(name, table, columns)


def upgrade() -> None:
    for table, create in ((STATE, _create_state), (TARGET, _create_target), (SNAPSHOT, _create_snapshot)):
        if not sa.inspect(op.get_bind()).has_table(table):
            create()
    _ensure_index(STATE, "uq_monitor_state_main_probe", ["probe_id"], main_only=True)
    _ensure_index(STATE, "ix_monitor_state_lease", ["probe_id", "cycle_lease_until"])
    _ensure_index(TARGET, "uq_monitor_target_main_host", ["pg_host_id"], main_only=True)
    _ensure_index(TARGET, "ix_monitor_target_due", ["reseller_id", "test_enabled", "next_check_at", "id"])
    _ensure_index(TARGET, "ix_monitor_target_public", ["reseller_id", "test_enabled", "is_public", "display_order", "id"])
    _ensure_index(TARGET, "ix_monitor_target_lease", ["reseller_id", "claim_until"])
    _ensure_index(SNAPSHOT, "ix_monitor_snapshot_scope_target", ["reseller_id", "target_id", "probe_id"])


def downgrade() -> None:
    for table in (SNAPSHOT, TARGET, STATE):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
