"""Take the connection status button out of menus that never set the feature up.

Revision ID: 0059_status_menu_default_off
Revises: 0058_monitor_subscription_configs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0059_status_menu_default_off"
down_revision: str | None = "0058_monitor_subscription_configs"
branch_labels: str | None = None
depends_on: str | None = None
MENU_KEY = "connection_status"
BATCH_SIZE = 200


def _without_status_button(value: str | None) -> str:
    order = [key.strip() for key in (value or "").split(",") if key.strip()]
    if MENU_KEY not in order:
        return value or ""
    return ",".join(key for key in order if key != MENU_KEY)


def _monitor_is_configured(connection: sa.Connection) -> bool:
    if not sa.inspect(connection).has_table("connection_monitor_states"):
        return False
    states = sa.table("connection_monitor_states", sa.column("reseller_id", sa.Integer), sa.column("pg_username", sa.String))
    return connection.execute(sa.select(states.c.reseller_id).where(
        states.c.reseller_id.is_(None), states.c.pg_username.is_not(None), states.c.pg_username != "",
    ).limit(1)).first() is not None


def _strip_menu_table(table_name: str) -> None:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table(table_name):
        return
    table = sa.table(table_name, sa.column("id", sa.Integer), sa.column("key", sa.String), sa.column("value", sa.Text))
    last_id = 0
    while rows := connection.execute(sa.select(table.c.id, table.c.value)
            .where(table.c.key == "menu_order", table.c.id > last_id).order_by(table.c.id).limit(BATCH_SIZE)).all():
        edits = [{"menu_id": row.id, "menu_value": updated} for row in rows
                 if (updated := _without_status_button(row.value)) != row.value]
        if edits:
            connection.execute(sa.update(table).where(table.c.id == sa.bindparam("menu_id"))
                               .values(value=sa.bindparam("menu_value")), edits)
        last_id = rows[-1].id


def upgrade() -> None:
    # Shops never configure the monitor, so the button only ever led them to an empty page.
    _strip_menu_table("reseller_settings")
    # The platform keeps its button when the owner already registered a test user.
    if not _monitor_is_configured(op.get_bind()):
        _strip_menu_table("settings")


def downgrade() -> None:
    # Menu choices are user data: keep them, including later administrator edits.
    return None
