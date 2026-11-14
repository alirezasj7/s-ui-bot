"""Exclude demo customers from business reports without deleting their history."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_demo_users"
down_revision = "0040_contacts_cancel_notices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("bot_users")}
    if "is_demo" not in columns:
        op.add_column("bot_users", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("bot_users")}
    if "ix_bot_users_is_demo" not in indexes:
        op.create_index("ix_bot_users_is_demo", "bot_users", ["is_demo"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("bot_users")}
    if "ix_bot_users_is_demo" in indexes:
        op.drop_index("ix_bot_users_is_demo", table_name="bot_users")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("bot_users")}
    if "is_demo" in columns:
        with op.batch_alter_table("bot_users") as batch:
            batch.drop_column("is_demo")
