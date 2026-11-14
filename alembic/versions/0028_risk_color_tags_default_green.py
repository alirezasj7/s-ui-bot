"""Unify color_tag into 4 risk levels; default green for all bot_users.

Revision ID: 0028_risk_color_tags_default_green
Revises: 0027_bot_users_color_tag
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0028_risk_color_tags_default_green"
down_revision: str = "0027_bot_users_color_tag"
branch_labels = None
depends_on = None

_VALID = ("green", "yellow", "orange", "red")


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("bot_users")}
    if "color_tag" not in cols:
        op.add_column(
            "bot_users",
            sa.Column("color_tag", sa.String(length=16), nullable=True),
        )
        op.create_index("ix_bot_users_color_tag", "bot_users", ["color_tag"])

    # Map legacy palette → 4 risk levels; fill NULL → green.
    op.execute(
        sa.text(
            """
            UPDATE bot_users
            SET color_tag = CASE
              WHEN lower(coalesce(color_tag, '')) IN ('red') THEN 'red'
              WHEN lower(coalesce(color_tag, '')) IN ('orange') THEN 'orange'
              WHEN lower(coalesce(color_tag, '')) IN ('yellow', 'amber') THEN 'yellow'
              WHEN lower(coalesce(color_tag, '')) IN ('green') THEN 'green'
              ELSE 'green'
            END
            """
        )
    )


def downgrade() -> None:
    # Keep data; no destructive downgrade of values.
    pass
