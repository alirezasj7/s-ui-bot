"""Index bot_users.reseller_id — every reseller-scoped user query filters on it.

Revision ID: 0010_bot_users_reseller_id_index
Revises: 0009_ux20_ops_features
Create Date: 2026-08-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_bot_users_reseller_id_index"
down_revision: Union[str, None] = "0009_ux20_ops_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_bot_users_reseller_id"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("bot_users"):
        return
    existing = {ix["name"] for ix in insp.get_indexes("bot_users")}
    if INDEX_NAME not in existing:
        op.create_index(INDEX_NAME, "bot_users", ["reseller_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("bot_users"):
        return
    existing = {ix["name"] for ix in insp.get_indexes("bot_users")}
    if INDEX_NAME in existing:
        op.drop_index(INDEX_NAME, table_name="bot_users")
