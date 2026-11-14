"""Encrypt-at-rest support for reseller bot tokens (hash lookup column).

Revision ID: 0026_reseller_bot_token_hash
Revises: 0025_terms_acceptances
Create Date: 2026-09-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_reseller_bot_token_hash"
down_revision: Union[str, None] = "0025_terms_acceptances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
    if "bot_token_hash" not in cols:
        op.add_column(
            "reseller_profiles",
            sa.Column("bot_token_hash", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_reseller_profiles_bot_token_hash",
            "reseller_profiles",
            ["bot_token_hash"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
    if "bot_token_hash" in cols:
        op.drop_index("ix_reseller_profiles_bot_token_hash", table_name="reseller_profiles")
        op.drop_column("reseller_profiles", "bot_token_hash")
