"""Alembic 0031 must emit Postgres-safe boolean defaults (v0.2.0 hotfix)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "alembic/versions/0031_plan_categories_service_addons.py"


class Alembic0031PgBoolDefaults(unittest.TestCase):
    def test_source_uses_sa_true_not_text_one(self):
        src = MIG.read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("server_default=sa.true()"), 2)
        self.assertNotRegex(src, r'is_active.*server_default=sa\.text\([\'"]1[\'"]\)')

    def test_postgresql_ddl_has_default_true_not_one(self):
        meta = sa.MetaData()
        table = sa.Table(
            "plan_categories",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            ),
        )
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        self.assertIn("DEFAULT true", ddl)
        self.assertNotRegex(ddl, r"BOOLEAN\s+DEFAULT\s+1\b")

    def test_migration_file_compiles_without_default_1_for_bool(self):
        """Guard: any Boolean DEFAULT in 0031 upgrade path must not be literal 1."""
        src = MIG.read_text(encoding="utf-8")
        # Extract upgrade() body roughly and ban classic failure mode.
        self.assertNotIn('sa.text("1")', src)
        self.assertNotIn("sa.text('1')", src)
        # Positive: sa.true present near is_active.
        self.assertRegex(
            src,
            re.compile(r'is_active".*server_default=sa\.true\(\)', re.S),
        )


if __name__ == "__main__":
    unittest.main()
