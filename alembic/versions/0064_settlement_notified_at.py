"""Record when a settled payment's delivery was sent, so it is sent only once.

Revision ID: 0064_settlement_notified_at
Revises: 0063_orders_created_at_index

The «بزن به کارت» callback, its return page and the background poll can all see the same
settlement settle; ``notified_at`` is claimed atomically by the one that sends the delivery.
Settlements that are already settled are marked as notified, so the upgrade never resends
an old delivery. Idempotent; the downgrade drops the column and keeps every row.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0064_settlement_notified_at"
down_revision: Union[str, None] = "0063_orders_created_at_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "payment_settlements"
COLUMN = "notified_at"


def _columns(bind: sa.Connection) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True))
    bind.execute(
        sa.text("UPDATE payment_settlements SET notified_at = COALESCE(settled_at, updated_at) WHERE status = 'settled'")
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or COLUMN not in _columns(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
