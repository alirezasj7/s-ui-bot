"""Requests to add an existing service that wait for admin approval.

Revision ID: 0053_service_import_requests
Revises: 0052_service_import_reason
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0053_service_import_requests"
down_revision: Union[str, None] = "0052_service_import_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "service_import_requests"
OPEN_INDEX = "uq_service_import_requests_open"
SHOP_INDEX = "ix_service_import_requests_shop_status"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("bot_user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("shop_id", sa.Integer(), nullable=True),
            sa.Column("panel_user_id", sa.Integer(), nullable=False),
            sa.Column("panel_username", sa.String(128), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("reason", sa.String(32), nullable=True),
            sa.Column("decided_by", sa.String(64), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    existing = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if OPEN_INDEX not in existing:
        op.create_index(
            OPEN_INDEX, TABLE, ["bot_user_id", "panel_user_id"], unique=True,
            sqlite_where=sa.text("status = 'pending'"), postgresql_where=sa.text("status = 'pending'"),
        )
    if SHOP_INDEX not in existing:
        op.create_index(SHOP_INDEX, TABLE, ["shop_id", "status"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(TABLE):
        op.drop_table(TABLE)
