"""Support adding an existing panel service to «سرویس‌های من».

Adds the attempt log used for rate limiting and audit, and a partial unique index so
one panel user can be imported by one customer only.

Revision ID: 0051_service_import
Revises: 0050_addon_pack_general_scope
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0051_service_import"
down_revision: Union[str, None] = "0050_addon_pack_general_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ATTEMPTS = "service_import_attempts"
ATTEMPTS_INDEX = "ix_service_import_attempts_user_time"
SERVICES = "user_services"
IMPORTED_INDEX = "uq_user_services_imported_pg_user"
IMPORTED_WHERE = sa.text("remark = 'imported'")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(ATTEMPTS) and insp.has_table("bot_users"):
        op.create_table(
            ATTEMPTS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("bot_user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("outcome", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(ATTEMPTS_INDEX, ATTEMPTS, ["bot_user_id", "created_at"])
    if insp.has_table(SERVICES) and IMPORTED_INDEX not in {i["name"] for i in insp.get_indexes(SERVICES)}:
        op.create_index(
            IMPORTED_INDEX, SERVICES, ["pg_user_id"], unique=True,
            sqlite_where=IMPORTED_WHERE, postgresql_where=IMPORTED_WHERE,
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(SERVICES) and IMPORTED_INDEX in {i["name"] for i in insp.get_indexes(SERVICES)}:
        op.drop_index(IMPORTED_INDEX, table_name=SERVICES)
    if insp.has_table(ATTEMPTS):
        op.drop_table(ATTEMPTS)
