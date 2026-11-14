"""Keep the operator-facing reason of a refused «افزودن سرویس قبلی» try.

Revision ID: 0052_service_import_reason
Revises: 0051_service_import
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0052_service_import_reason"
down_revision: Union[str, None] = "0051_service_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ATTEMPTS = "service_import_attempts"
COLUMN = "reason"


def _has_column() -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table(ATTEMPTS) and COLUMN in {c["name"] for c in insp.get_columns(ATTEMPTS)}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table(ATTEMPTS) and not _has_column():
        with op.batch_alter_table(ATTEMPTS) as batch:
            batch.add_column(sa.Column(COLUMN, sa.String(32), nullable=True))


def downgrade() -> None:
    if _has_column():
        with op.batch_alter_table(ATTEMPTS) as batch:
            batch.drop_column(COLUMN)
