"""Add the customer status button to saved platform and shop menus.

Revision ID: 0057_connection_status_menu
Revises: 0056_monitor_account_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0057_connection_status_menu"
down_revision: str | None = "0056_monitor_account_identity"
branch_labels: str | None = None
depends_on: str | None = None
MENU_KEY = "connection_status"
BATCH_SIZE = 200


def _add_status_button(value: str | None) -> str:
    order = [key.strip() for key in (value or "").split(",") if key.strip()]
    if MENU_KEY in order:
        return value or ""
    anchor = "services" if "services" in order else "shop"
    position = order.index(anchor) + 1 if anchor in order else len(order)
    order.insert(position, MENU_KEY)
    return ",".join(order)


def _upgrade_menu_table(table_name: str) -> None:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table(table_name):
        return
    table = sa.table(table_name, sa.column("id", sa.Integer), sa.column("key", sa.String), sa.column("value", sa.Text))
    last_id = 0
    while rows := connection.execute(sa.select(table.c.id, table.c.value)
            .where(table.c.key == "menu_order", table.c.id > last_id).order_by(table.c.id).limit(BATCH_SIZE)).all():
        edits = [{"menu_id": row.id, "menu_value": updated} for row in rows
                 if (updated := _add_status_button(row.value)) != row.value]
        if edits:
            connection.execute(sa.update(table).where(table.c.id == sa.bindparam("menu_id"))
                               .values(value=sa.bindparam("menu_value")), edits)
        last_id = rows[-1].id


def upgrade() -> None:
    for table_name in ("settings", "reseller_settings"):
        _upgrade_menu_table(table_name)


def downgrade() -> None:
    # Menu choices are user data: keep them, including subsequent administrator edits.
    return None
