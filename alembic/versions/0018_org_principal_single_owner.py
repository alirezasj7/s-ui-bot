"""Alembic revision: singleton Owner principal (depth 0, parent NULL).

Revision ID: 0018_org_principal_single_owner
Revises: 0017_org_principal_bot_user_unique
Create Date: 2026-08-17

Partial unique index — at most one Owner row (any status). Does not rewrite
existing rows. Duplicate Owner rows cause this upgrade to fail rather than
silently merging identities. SQLite and PostgreSQL share the same SQL.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_org_principal_single_owner"
down_revision: Union[str, None] = "0017_org_principal_bot_user_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_principals_single_owner "
    "ON org_principals (depth) "
    "WHERE depth = 0 AND parent_id IS NULL"
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    names = {ix.get("name") for ix in insp.get_indexes("org_principals")}
    if "uq_org_principals_single_owner" in names:
        return
    op.execute(sa.text(INDEX_SQL))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("org_principals"):
        return
    names = {ix.get("name") for ix in insp.get_indexes("org_principals")}
    if "uq_org_principals_single_owner" not in names:
        return
    op.execute(sa.text("DROP INDEX IF EXISTS uq_org_principals_single_owner"))
