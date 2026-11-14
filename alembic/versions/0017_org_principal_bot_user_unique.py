"""Alembic revision: unique OrgPrincipal.bot_user_id (Phase 6A).

Revision ID: 0017_org_principal_bot_user_unique
Revises: 0016_org_principal_pg_password
Create Date: 2026-08-17

Partial unique index — multiple NULL bot_user_id values remain allowed.
Does not rewrite or reassign existing binds. Duplicate non-NULL values
cause this upgrade to fail rather than silently merging identities.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_org_principal_bot_user_unique"
down_revision: Union[str, None] = "0016_org_principal_pg_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_principals_bot_user_id "
    "ON org_principals (bot_user_id) "
    "WHERE bot_user_id IS NOT NULL"
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    names = {ix.get("name") for ix in insp.get_indexes("org_principals")}
    if "uq_org_principals_bot_user_id" in names:
        return
    op.execute(sa.text(INDEX_SQL))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    names = {ix.get("name") for ix in insp.get_indexes("org_principals")}
    if "uq_org_principals_bot_user_id" not in names:
        return
    op.execute(sa.text("DROP INDEX IF EXISTS uq_org_principals_bot_user_id"))
