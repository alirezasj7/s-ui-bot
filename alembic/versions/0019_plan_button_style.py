"""Per-plan Telegram button style override.

Revision ID: 0019_plan_button_style
Revises: 0018_org_principal_single_owner
Create Date: 2026-08-22

NULL = inherit plan-kind color from settings catalog.
Empty string = explicit Telegram default (white).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_plan_button_style"
down_revision: Union[str, None] = "0018_org_principal_single_owner"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: str, col_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column in cols:
        return
    op.add_column(table, sa.Column(column, col_type, nullable=True))


def upgrade() -> None:
    _add_column_if_missing("plans", "button_style", sa.String(16))
    _add_column_if_missing("reseller_plans", "button_style", sa.String(16))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("plans", "reseller_plans"):
        if not insp.has_table(table):
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "button_style" in cols:
            op.drop_column(table, "button_style")
