from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.bot.handlers import admin_backup


class _FakeBot:
    def __init__(self, *, payload: bytes | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    async def download(self, _doc: object, *, destination: Path) -> None:
        if self.error is not None:
            raise self.error
        await asyncio.to_thread(Path(destination).write_bytes, self.payload or b"")


class BackupUploadTempFileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp_path = Path(self._dir.name) / "upload.zip"
        self.tmp_path.touch()
        patcher = patch.object(admin_backup, "_new_temp_zip_path", return_value=str(self.tmp_path))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_returns_downloaded_bytes_and_removes_temp_file(self) -> None:
        content = await admin_backup._download_upload_bytes(_FakeBot(payload=b"zip-bytes"), object())

        self.assertEqual(content, b"zip-bytes")
        self.assertFalse(self.tmp_path.exists())

    async def test_failed_download_still_removes_temp_file(self) -> None:
        with self.assertRaises(RuntimeError):
            await admin_backup._download_upload_bytes(_FakeBot(error=RuntimeError("network")), object())

        self.assertFalse(self.tmp_path.exists())


if __name__ == "__main__":
    unittest.main()
