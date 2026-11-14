"""Link PAYG billing to shop wallet (payg_wallet_linked flag).

Revision ID: 0006_payg_wallet_linked
Revises: 0005_payg_suspend_plan_addons
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_payg_wallet_linked"
down_revision: Union[str, None] = "0005_payg_suspend_plan_addons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_profiles"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
    if "payg_wallet_linked" not in cols:
        op.add_column(
            "reseller_profiles",
            sa.Column("payg_wallet_linked", sa.Boolean(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("reseller_profiles"):
        return
    cols = {c["name"] for c in insp.get_columns("reseller_profiles")}
    if "payg_wallet_linked" in cols:
        op.drop_column("reseller_profiles", "payg_wallet_linked")
