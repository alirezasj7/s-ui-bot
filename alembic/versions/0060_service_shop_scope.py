"""Store the selling shop on each service and add the shop membership table.

Revision ID: 0060_service_shop_scope
Revises: 0059_status_menu_default_off

Backfill (first run only, bounded keyset batches, SQLite and PostgreSQL):

* a service created by an order takes the order's shop;
* any other service (imported, linked, manual, malformed remark) takes the
  customer's current shop only when that agrees with everything else the customer
  bought; otherwise it is left unassigned and marked ``shop_needs_review`` so no
  shop sees or manages it until the owner assigns it;
* ``bot_user_shops`` is filled from the customer's attribution, orders and services.

The downgrade drops what this revision added and keeps every existing row.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060_service_shop_scope"
down_revision: Union[str, None] = "0059_status_menu_default_off"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

BATCH_SIZE = 500
REVIEW_LOG_LIMIT = 200
ORDER_REMARK_PREFIX = "order:"
SERVICES = "user_services"
MEMBERS = "bot_user_shops"
SHOP_INDEX = "ix_user_services_shop_id"
REVIEW_INDEX = "ix_user_services_shop_needs_review"
MEMBER_SHOP_UNIQUE = "uq_bot_user_shops_shop"
MEMBER_PLATFORM_UNIQUE = "uq_bot_user_shops_platform"
MEMBER_SHOP_USER = "ix_bot_user_shops_shop_user"


def _order_id(remark: str | None) -> int | None:
    text = (remark or "").strip()
    if not text.startswith(ORDER_REMARK_PREFIX):
        return None
    try:
        return int(text.split(":", 1)[1].split()[0])
    except (ValueError, IndexError):
        return -1  # marks a malformed remark: unresolved, never a guess


def _in(connection: sa.Connection, sql: str, ids: Iterable[int], **params: object) -> list[sa.Row]:
    values = sorted(set(int(i) for i in ids))
    if not values:
        return []
    statement = sa.text(sql).bindparams(sa.bindparam("ids", expanding=True))
    return list(connection.execute(statement, {"ids": values, **params}))


def _backfill_services(connection: sa.Connection) -> tuple[list[int], list[int]]:
    """Set shop_id / shop_needs_review in keyset batches.

    Returns the ids left under review and the ids of order-less services that were given
    their customer's shop on the strength of the attribution alone (the owner can audit these).
    """
    review_ids: list[int] = []
    guessed_ids: list[int] = []
    last_id = 0
    while True:
        rows = connection.execute(
            sa.text("SELECT id, bot_user_id, remark FROM user_services WHERE id > :last ORDER BY id LIMIT :n"),
            {"last": last_id, "n": BATCH_SIZE},
        ).all()
        if not rows:
            return review_ids, guessed_ids
        last_id = int(rows[-1].id)
        order_ids = {oid for oid in (_order_id(r.remark) for r in rows) if oid and oid > 0}
        orders = {
            int(o.id): o
            for o in _in(connection, "SELECT id, user_id, reseller_id FROM orders WHERE id IN :ids", order_ids)
        }
        user_ids = {int(r.bot_user_id) for r in rows}
        attribution = {
            int(u.id): u.reseller_id
            for u in _in(connection, "SELECT id, reseller_id FROM bot_users WHERE id IN :ids", user_ids)
        }
        evidence: dict[int, set[int | None]] = {}
        for o in _in(
            connection, "SELECT DISTINCT user_id, reseller_id FROM orders WHERE user_id IN :ids", user_ids
        ):
            evidence.setdefault(int(o.user_id), set()).add(o.reseller_id)

        updates: list[dict[str, object]] = []
        for row in rows:
            order_id = _order_id(row.remark)
            shop: int | None
            review = False
            if order_id is not None:
                order = orders.get(order_id)
                if order is not None and int(order.user_id) == int(row.bot_user_id):
                    shop = order.reseller_id
                else:
                    shop, review = None, True
            else:
                customer_shop = attribution.get(int(row.bot_user_id))
                if evidence.get(int(row.bot_user_id), set()) <= {customer_shop}:
                    shop = customer_shop
                else:
                    shop, review = None, True
            if shop is not None or review:
                updates.append({"id": int(row.id), "shop": shop, "review": review})
            if review:
                review_ids.append(int(row.id))
            elif order_id is None and shop is not None:
                guessed_ids.append(int(row.id))
        if updates:
            connection.execute(
                sa.text("UPDATE user_services SET shop_id = :shop, shop_needs_review = :review WHERE id = :id"),
                updates,
            )


def _backfill_members(connection: sa.Connection) -> None:
    last_id = 0
    while True:
        users = connection.execute(
            sa.text("SELECT id, reseller_id FROM bot_users WHERE id > :last ORDER BY id LIMIT :n"),
            {"last": last_id, "n": BATCH_SIZE},
        ).all()
        if not users:
            return
        last_id = int(users[-1].id)
        ids = [int(u.id) for u in users]
        pairs: dict[int, set[int | None]] = {int(u.id): {u.reseller_id} for u in users}
        for o in _in(
            connection, "SELECT DISTINCT user_id, reseller_id FROM orders WHERE user_id IN :ids", ids
        ):
            pairs[int(o.user_id)].add(o.reseller_id)
        for s in _in(
            connection,
            "SELECT DISTINCT bot_user_id, shop_id FROM user_services "
            "WHERE bot_user_id IN :ids AND shop_needs_review = :review",
            ids,
            review=False,
        ):
            pairs[int(s.bot_user_id)].add(s.shop_id)
        inserts = [
            {"user": uid, "shop": shop} for uid, shops in pairs.items() for shop in shops
        ]
        connection.execute(
            sa.text("INSERT INTO bot_user_shops (bot_user_id, shop_id) VALUES (:user, :shop)"), inserts
        )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(SERVICES):
        return
    columns = {c["name"] for c in inspector.get_columns(SERVICES)}
    indexes = {i["name"] for i in inspector.get_indexes(SERVICES)}
    first_run = "shop_id" not in columns
    if first_run:
        # SQLite cannot add a constraint to an existing table; a table rebuild is not worth
        # it for a nullable column (SQLite does not enforce the foreign key by default).
        references = [] if connection.dialect.name == "sqlite" else [sa.ForeignKey("bot_users.id")]
        op.add_column(SERVICES, sa.Column("shop_id", sa.Integer(), *references, nullable=True))
    if "shop_needs_review" not in columns:
        op.add_column(
            SERVICES,
            sa.Column("shop_needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if SHOP_INDEX not in indexes:
        op.create_index(SHOP_INDEX, SERVICES, ["shop_id"])
    if REVIEW_INDEX not in indexes:
        op.create_index(REVIEW_INDEX, SERVICES, ["shop_needs_review"])

    created_members = not inspector.has_table(MEMBERS)
    if created_members:
        op.create_table(
            MEMBERS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("bot_user_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("shop_id", sa.Integer(), sa.ForeignKey("bot_users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            MEMBER_SHOP_UNIQUE, MEMBERS, ["bot_user_id", "shop_id"], unique=True,
            sqlite_where=sa.text("shop_id IS NOT NULL"), postgresql_where=sa.text("shop_id IS NOT NULL"),
        )
        op.create_index(
            MEMBER_PLATFORM_UNIQUE, MEMBERS, ["bot_user_id"], unique=True,
            sqlite_where=sa.text("shop_id IS NULL"), postgresql_where=sa.text("shop_id IS NULL"),
        )
        op.create_index(MEMBER_SHOP_USER, MEMBERS, ["shop_id", "bot_user_id"])

    if first_run and inspector.has_table("orders") and inspector.has_table("bot_users"):
        review_ids, guessed_ids = _backfill_services(connection)
        if guessed_ids:
            logger.warning(
                "%d service(s) without an order were assigned to their customer's shop from the "
                "attribution alone; audit them if a customer was attributed after buying elsewhere: %s",
                len(guessed_ids), guessed_ids[:REVIEW_LOG_LIMIT],
            )
        if review_ids:
            logger.warning(
                "%d service(s) have no derivable shop and are hidden until assigned: %s",
                len(review_ids), review_ids[:REVIEW_LOG_LIMIT],
            )
    if created_members and inspector.has_table("bot_users"):
        _backfill_members(connection)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if inspector.has_table(MEMBERS):
        for name in (MEMBER_SHOP_USER, MEMBER_PLATFORM_UNIQUE, MEMBER_SHOP_UNIQUE):
            op.drop_index(name, table_name=MEMBERS)
        op.drop_table(MEMBERS)
    if not inspector.has_table(SERVICES):
        return
    columns = {c["name"] for c in inspector.get_columns(SERVICES)}
    indexes = {i["name"] for i in inspector.get_indexes(SERVICES)}
    if REVIEW_INDEX in indexes:
        op.drop_index(REVIEW_INDEX, table_name=SERVICES)
    if SHOP_INDEX in indexes:
        op.drop_index(SHOP_INDEX, table_name=SERVICES)
    with op.batch_alter_table(SERVICES) as batch:
        if "shop_needs_review" in columns:
            batch.drop_column("shop_needs_review")
        if "shop_id" in columns:
            batch.drop_column("shop_id")
