"""Keep loyalty points per shop (shop_points) and record the shop on each points entry.

Revision ID: 0061_shop_points
Revises: 0060_service_shop_scope

Until now every customer had one balance (``bot_users.points_balance``) although
earn rules and rewards are per shop. On the first run, the points of a customer
attributed to a shop move to that shop's row and the entries of that customer are
stamped with the shop; everyone else keeps the platform balance. The downgrade adds
the shop balances back to ``bot_users.points_balance`` and drops what was added.
"""

from __future__ import annotations

from typing import Sequence, Union

import logging

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "0061_shop_points"
down_revision: Union[str, None] = "0060_service_shop_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BATCH_SIZE = 2000
SHOP_POINTS = "shop_points"
TRANSACTIONS = "points_transactions"
TX_INDEX = "ix_points_transactions_reseller_id"


def _ranges(connection: sa.Connection, table: str) -> list[tuple[int, int]]:
    top = connection.execute(sa.text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")).scalar() or 0  # fixed table names
    return [(low, min(low + BATCH_SIZE, int(top))) for low in range(0, int(top), BATCH_SIZE)]


def _move_points_to_shops(connection: sa.Connection) -> None:
    moved = connection.execute(
        sa.text(
            "SELECT COUNT(*), COALESCE(SUM(points_balance), 0) FROM bot_users "
            "WHERE reseller_id IS NOT NULL AND points_balance <> 0"
        )
    ).one()
    if moved[0]:
        logger.warning(
            "%d customer(s) attributed to a shop had %d points moved from the platform balance to that shop",
            moved[0], moved[1],
        )
    for low, high in _ranges(connection, "bot_users"):
        window = {"low": low, "high": high}
        connection.execute(
            sa.text(
                "INSERT INTO shop_points (user_id, reseller_id, balance) "
                "SELECT id, reseller_id, points_balance FROM bot_users "
                "WHERE id > :low AND id <= :high AND reseller_id IS NOT NULL AND points_balance <> 0"
            ),
            window,
        )
        connection.execute(
            sa.text(
                "UPDATE bot_users SET points_balance = 0 "
                "WHERE id > :low AND id <= :high AND reseller_id IS NOT NULL AND points_balance <> 0"
            ),
            window,
        )


def _stamp_entries(connection: sa.Connection) -> None:
    for low, high in _ranges(connection, TRANSACTIONS):
        connection.execute(
            sa.text(
                "UPDATE points_transactions SET reseller_id = "
                "(SELECT reseller_id FROM bot_users WHERE bot_users.id = points_transactions.user_id) "
                "WHERE id > :low AND id <= :high AND reseller_id IS NULL"
            ),
            {"low": low, "high": high},
        )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(TRANSACTIONS) or not inspector.has_table("bot_users"):
        return
    first_run = not inspector.has_table(SHOP_POINTS)
    columns = {c["name"] for c in inspector.get_columns(TRANSACTIONS)}
    if "reseller_id" not in columns:
        references = [] if connection.dialect.name == "sqlite" else [sa.ForeignKey("bot_users.id")]
        op.add_column(TRANSACTIONS, sa.Column("reseller_id", sa.Integer(), *references, nullable=True))
    if TX_INDEX not in {i["name"] for i in inspector.get_indexes(TRANSACTIONS)}:
        op.create_index(TX_INDEX, TRANSACTIONS, ["reseller_id"])
    if first_run:
        op.create_table(
            SHOP_POINTS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reseller_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("user_id", "reseller_id", name="uq_shop_points_user_reseller"),
        )
        op.create_index("ix_shop_points_user_id", SHOP_POINTS, ["user_id"])
        op.create_index("ix_shop_points_reseller_id", SHOP_POINTS, ["reseller_id"])
        _move_points_to_shops(connection)
        _stamp_entries(connection)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if inspector.has_table(SHOP_POINTS):
        for low, high in _ranges(connection, "bot_users"):
            connection.execute(
                sa.text(
                    "UPDATE bot_users SET points_balance = points_balance + COALESCE("
                    "(SELECT SUM(balance) FROM shop_points WHERE shop_points.user_id = bot_users.id), 0) "
                    "WHERE id > :low AND id <= :high"
                ),
                {"low": low, "high": high},
            )
        op.drop_index("ix_shop_points_reseller_id", table_name=SHOP_POINTS)
        op.drop_index("ix_shop_points_user_id", table_name=SHOP_POINTS)
        op.drop_table(SHOP_POINTS)
    if inspector.has_table(TRANSACTIONS):
        if TX_INDEX in {i["name"] for i in inspector.get_indexes(TRANSACTIONS)}:
            op.drop_index(TX_INDEX, table_name=TRANSACTIONS)
        if "reseller_id" in {c["name"] for c in inspector.get_columns(TRANSACTIONS)}:
            with op.batch_alter_table(TRANSACTIONS) as batch:
                batch.drop_column("reseller_id")
