"""Baseline schema matching app.db.models (PGClock 3.8.3 + Phase A).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-04

Creates the full application schema via SQLAlchemy metadata and adds the
referral partial unique index required for wallet race protection.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db import Base
import app.db.models  # noqa: F401

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFERRAL_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_referral_reason "
    "ON wallet_transactions (user_id, reason) "
    "WHERE reason LIKE 'referral:%'"
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Partial unique index is not declared on the ORM model (SQLite/PG both support it).
    op.execute(sa.text(REFERRAL_INDEX))


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("DROP INDEX IF EXISTS uq_wallet_referral_reason"))
    Base.metadata.drop_all(bind=bind)
