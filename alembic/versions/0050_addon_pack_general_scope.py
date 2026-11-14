"""Mark add-on packs that apply to every plan category.

Packs without a category used to match only services without a category. They now
mean "general": every pack that has no category keeps working and also applies to
categorized services, while a pack tied to a category stays tied to it. The flag is
explicit so deleting a category can never widen a category's pack to everyone.

Revision ID: 0050_addon_pack_general_scope
Revises: 0049_payg_tick_issue
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050_addon_pack_general_scope"
down_revision: Union[str, None] = "0049_payg_tick_issue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "service_addon_packs"
COLUMN = "is_general"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(TABLE):
        return
    if COLUMN in {c["name"] for c in insp.get_columns(TABLE)}:
        return
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Every existing row starts general; packs tied to a category keep that scope.
    if "category_id" in {c["name"] for c in insp.get_columns(TABLE)}:
        bind.execute(sa.text(f"UPDATE {TABLE} SET {COLUMN} = :general WHERE category_id IS NOT NULL").bindparams(general=False))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return
    if COLUMN not in {c["name"] for c in insp.get_columns(TABLE)}:
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
