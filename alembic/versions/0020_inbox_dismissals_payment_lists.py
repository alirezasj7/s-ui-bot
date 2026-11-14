"""Panel inbox dismissals for snooze/hide alerts.

Revision ID: 0020_inbox_dismissals
Revises: 0019_plan_button_style
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_inbox_dismissals"
down_revision: Union[str, None] = "0019_plan_button_style"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("panel_inbox_dismissals"):
        return
    op.create_table(
        "panel_inbox_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("staff_key", sa.String(128), nullable=False),
        sa.Column("alert_key", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "staff_key",
            "alert_key",
            "entity_id",
            name="uq_panel_inbox_dismiss_staff_alert",
        ),
    )
    op.create_index(
        "ix_panel_inbox_dismissals_staff_key",
        "panel_inbox_dismissals",
        ["staff_key"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("panel_inbox_dismissals"):
        return
    op.drop_index("ix_panel_inbox_dismissals_staff_key", table_name="panel_inbox_dismissals")
    op.drop_table("panel_inbox_dismissals")
