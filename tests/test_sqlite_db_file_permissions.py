"""Regression test: the SQLite database file must be locked to 0600.

``bot.db`` holds encrypted PasarGuard admin passwords, session-adjacent data,
and every reseller/customer record. Previously only the containing directory
was chmod'd to 0700 — the file itself kept whatever permissions the SQLite
driver created it with (which can be as loose as 0644 depending on umask),
so a misconfigured backup/export step or a sibling process running under a
different user could still read it directly. The sqlite ``connect`` event
must now also pin the db file (and any -wal/-shm/-journal siblings) to 0600.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SqliteDbFilePermissionsTests(unittest.TestCase):
    def test_connect_hook_chmods_db_file_to_0600(self):
        from app.db import session as db_session

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "bot.db"
            db_path.write_text("", encoding="utf-8")
            db_path.chmod(0o644)
            wal = db_path.with_name(db_path.name + "-wal")
            wal.write_text("", encoding="utf-8")
            wal.chmod(0o644)

            fake_info = type(db_session._engine_info)(
                dialect="sqlite",
                url="sqlite+aiosqlite:///" + str(db_path),
                is_sqlite=True,
                is_postgresql=False,
                sqlite_path=db_path,
            )
            with patch.object(db_session, "_engine_info", fake_info):
                db_session._sqlite_on_connect(_FakeDbApiConn(), None)

            mode = stat.S_IMODE(db_path.stat().st_mode)
            self.assertEqual(mode, 0o600, f"expected 0600, got {oct(mode)}")
            wal_mode = stat.S_IMODE(wal.stat().st_mode)
            self.assertEqual(wal_mode, 0o600)

    def test_connect_hook_tolerates_missing_file(self):
        from app.db import session as db_session

        fake_info = type(db_session._engine_info)(
            dialect="sqlite",
            url="sqlite+aiosqlite:///does/not/exist.db",
            is_sqlite=True,
            is_postgresql=False,
            sqlite_path=Path("/nonexistent/does-not-exist.db"),
        )
        with patch.object(db_session, "_engine_info", fake_info):
            # Must not raise even though the path does not exist.
            db_session._sqlite_on_connect(_FakeDbApiConn(), None)


class _FakeCursor:
    def execute(self, *_a, **_k):
        return None

    def close(self):
        return None


class _FakeDbApiConn:
    def cursor(self):
        return _FakeCursor()


if __name__ == "__main__":
    unittest.main()
