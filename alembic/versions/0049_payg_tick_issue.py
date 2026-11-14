"""Remember which billing problem was last announced for a PAYG reseller.

Revision ID: 0049_payg_tick_issue
Revises: 0048_payg_low_balance_level
Create Date: 2026-10-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_payg_tick_issue"
down_revision: Union[str, None] = "0048_payg_low_balance_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "reseller_profiles"
COLUMN = "billing_tick_issue"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return
    if COLUMN in {c["name"] for c in insp.get_columns(TABLE)}:
        return
    op.add_column(TABLE, sa.Column(COLUMN, sa.String(32), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return
    if COLUMN not in {c["name"] for c in insp.get_columns(TABLE)}:
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
