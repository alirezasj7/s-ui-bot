"""Index orders by creation time for the dashboard period and trend queries.

Revision ID: 0063_orders_created_at_index
Revises: 0062_wheel_state_per_shop

The dashboard sums delivered revenue over the last 7, 30 and 60 days; without this index
each refresh scans the whole ``orders`` table. The upgrade is idempotent and the downgrade
only drops the index.

On PostgreSQL the index is built with ``CREATE INDEX CONCURRENTLY`` outside the migration
transaction, so the bot keeps writing orders while a large table is indexed. An interrupted
concurrent build leaves an invalid index behind; it is dropped and rebuilt on the next run.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063_orders_created_at_index"
down_revision: Union[str, None] = "0062_wheel_state_per_shop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "orders"
INDEX = "ix_orders_created_at"


def _index_names(bind: sa.Connection) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(TABLE)}


def _postgres_index_is_invalid(bind: sa.Connection) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT NOT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :name AND pg_catalog.pg_table_is_visible(c.oid)"
        ),
        {"name": INDEX},
    ).first()
    return bool(row and row[0])


def _upgrade_postgres(bind: sa.Connection) -> None:
    with op.get_context().autocommit_block():
        if _postgres_index_is_invalid(bind):
            op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
        if INDEX not in _index_names(bind):
            op.create_index(INDEX, TABLE, ["created_at"], postgresql_concurrently=True)


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    if bind.dialect.name == "postgresql":
        _upgrade_postgres(bind)
    elif INDEX not in _index_names(bind):
        op.create_index(INDEX, TABLE, ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE) or INDEX not in _index_names(bind):
        return
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
    else:
        op.drop_index(INDEX, table_name=TABLE)
