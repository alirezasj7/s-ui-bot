"""Add staff color_tag on bot_users for list scanning.

Revision ID: 0027_bot_users_color_tag
Revises: 0026_reseller_bot_token_hash
Create Date: 2026-09-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_bot_users_color_tag"
down_revision: Union[str, None] = "0026_reseller_bot_token_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("bot_users")}
    if "color_tag" not in cols:
        op.add_column(
            "bot_users",
            sa.Column("color_tag", sa.String(length=16), nullable=True),
        )
        op.create_index("ix_bot_users_color_tag", "bot_users", ["color_tag"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("bot_users")}
    if "color_tag" in cols:
        op.drop_index("ix_bot_users_color_tag", table_name="bot_users")
        op.drop_column("bot_users", "color_tag")
