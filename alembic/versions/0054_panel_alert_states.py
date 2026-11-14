"""State of panel alerts that are pushed to Telegram (announce each change once).

Revision ID: 0054_panel_alert_states
Revises: 0053_service_import_requests
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_panel_alert_states"
down_revision: Union[str, None] = "0053_service_import_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "panel_alert_states"
INDEX = "uq_panel_alert_states_scope_alert"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope_key", sa.String(32), nullable=False),
            sa.Column("alert", sa.String(32), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("last_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fingerprint", sa.String(64), nullable=False, server_default=""),
            sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        )
    existing = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if INDEX not in existing:
        op.create_index(INDEX, TABLE, ["scope_key", "alert"], unique=True)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        op.drop_table(TABLE)
