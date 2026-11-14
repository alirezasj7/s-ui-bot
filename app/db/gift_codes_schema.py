"""Additive gift-code upgrade shared by Alembic and pre-Alembic databases."""

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn


def upgrade_gift_codes(connection) -> None:
    from app.db.models import ChargeCode, ChargeCodeUse

    inspector = inspect(connection)
    if not inspector.has_table("charge_codes"):
        ChargeCode.__table__.create(connection)
    existing = {col["name"] for col in inspector.get_columns("charge_codes")}
    for name in (
        "kind",
        "percent",
        "max_discount_toman",
        "expires_at",
        "max_uses_per_user",
        "first_purchase_only",
        "purchase_types",
    ):
        if name not in existing:
            column = str(
                CreateColumn(ChargeCode.__table__.c[name]).compile(
                    dialect=connection.dialect
                )
            )
            connection.execute(text(f"ALTER TABLE charge_codes ADD COLUMN {column}"))
    if not inspector.has_table("charge_code_uses"):
        ChargeCodeUse.__table__.create(connection)
        # Prefer the limits-era per-user ledger when it already has rows (0036 on
        # dev). Otherwise reconstruct from wallet credit reasons (main installs).
        redemption_rows = 0
        if inspector.has_table("charge_code_redemptions"):
            redemption_rows = int(
                connection.execute(
                    text("SELECT COUNT(*) FROM charge_code_redemptions")
                ).scalar()
                or 0
            )
        if redemption_rows:
            connection.execute(
                text("""
                INSERT INTO charge_code_uses (charge_code_id, user_id, status, created_at)
                SELECT r.code_id, r.user_id, 'consumed', r.created_at
                FROM charge_code_redemptions r
            """)
            )
        elif inspector.has_table("wallet_transactions"):
            connection.execute(
                text("""
                INSERT INTO charge_code_uses (charge_code_id, user_id, status, created_at)
                SELECT c.id, w.user_id, 'consumed', w.created_at
                FROM wallet_transactions w JOIN charge_codes c
                  ON w.reason = 'کد هدیه ' || c.code
                WHERE w.amount > 0
            """)
            )
