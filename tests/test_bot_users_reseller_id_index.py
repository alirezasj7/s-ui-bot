"""``bot_users.reseller_id`` — filtered by every reseller-scoped query (tenant
isolation: bot's "my customers" list, dashboards, finance) — must be indexed,
both in the ORM model and via an Alembic migration so existing databases
pick it up on upgrade.
"""

from __future__ import annotations

import unittest


class BotUsersResellerIdIndexTests(unittest.TestCase):
    def test_model_column_is_indexed(self):
        from app.db.models import BotUser

        col = BotUser.__table__.c.reseller_id
        self.assertTrue(
            col.index, "bot_users.reseller_id must be indexed (tenant-isolation queries filter on it)"
        )

    def test_migration_creates_index_on_sqlite(self):
        import tempfile
        from pathlib import Path

        from sqlalchemy import create_engine, inspect

        from app.db.alembic_runner import upgrade_head

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "idx.db"
            url = f"sqlite+aiosqlite:///{db_path}"
            upgrade_head(url)
            sync_eng = create_engine(f"sqlite:///{db_path}")
            try:
                insp = inspect(sync_eng)
                names = {ix["name"] for ix in insp.get_indexes("bot_users")}
                self.assertIn("ix_bot_users_reseller_id", names)
            finally:
                sync_eng.dispose()

    def test_ensure_indexes_statement_present(self):
        """Legacy pre-Alembic SQLite bootstrap path must also get this index."""
        from pathlib import Path

        src = Path("app/db/session.py").read_text(encoding="utf-8")
        self.assertIn("ix_bot_users_reseller_id ON bot_users (reseller_id)", src)


if __name__ == "__main__":
    unittest.main()
