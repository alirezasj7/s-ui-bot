"""Remember how many items an inbox alert covered when it was dismissed."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_inbox_dismiss_seen_count"
down_revision = "0046_catalog_discounts"
branch_labels = None
depends_on = None

TABLE = "panel_inbox_dismissals"
COLUMN = "seen_count"


def _has_column(bind) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return False
    return any(col["name"] == COLUMN for col in inspector.get_columns(TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or _has_column(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(COLUMN, sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
