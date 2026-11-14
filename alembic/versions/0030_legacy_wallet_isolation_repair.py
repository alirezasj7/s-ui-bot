"""Repair pre-isolation shop wallet ledger (N2/N3).

Revision ID: 0030_legacy_wallet_isolation_repair
Revises: 0029_shop_wallets_isolation

- Deactivate oversized / unlimited shop gift codes.
- Claw back shop-sourced synthetic credits still on the platform purse.
- Move real shop top-up credits into ``shop_wallets``.
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.orm import sessionmaker

revision: str = "0030_legacy_wallet_isolation_repair"
down_revision: str = "0029_shop_wallets_isolation"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    Session = sessionmaker(bind=bind)
    session = Session()
    try:
        from app.services.wallet_isolation_migrate import (
            repair_legacy_wallet_isolation_sync,
        )

        stats = repair_legacy_wallet_isolation_sync(session)
        session.commit()
        logger.info("0030 legacy wallet repair done: %s", stats)
    except Exception:
        session.rollback()
        # Non-fatal: schema isolation (0029) already blocks new minting.
        # Operators can re-run the sync helper if a live DB needs a retry.
        logger.exception("0030 legacy wallet repair failed (non-fatal)")
    finally:
        session.close()


def downgrade() -> None:
    # Ledger repair is intentionally one-way.
    pass
