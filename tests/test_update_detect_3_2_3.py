"""Update detection: cache-bust VERSION + releases/latest fallback (3.2.3)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.updates import check_github_update, clear_update_cache


class _FakeResp:
    def __init__(self, status_code: int, *, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class UpdateDetectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_update_cache()

    async def test_picks_newer_of_version_file_and_release(self):
        async def fake_get(url, **kwargs):
            if "VERSION" in str(url):
                return _FakeResp(200, text="3.2.1\n")
            if str(url).endswith("/releases/latest"):
                return _FakeResp(200, json_data={"tag_name": "v3.2.2"})
            return _FakeResp(404)

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="3.2.0"
        ):
            info = await check_github_update(force=True)

        self.assertTrue(info["checked"])
        self.assertEqual(info["remote_version"], "3.2.2")
        self.assertTrue(info["update_available"])

    async def test_release_fallback_when_version_file_fails(self):
        async def fake_get(url, **kwargs):
            if "VERSION" in str(url):
                raise RuntimeError("blocked")
            if str(url).endswith("/releases/latest"):
                return _FakeResp(200, json_data={"tag_name": "v3.2.2"})
            return _FakeResp(404)

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="3.2.1"
        ):
            info = await check_github_update(force=True)

        self.assertTrue(info["checked"])
        self.assertEqual(info["remote_version"], "3.2.2")
        self.assertTrue(info["update_available"])

    async def test_always_sends_cache_buster_on_version_url(self):
        calls: list[dict] = []

        async def fake_get(url, **kwargs):
            calls.append({"url": str(url), "params": kwargs.get("params")})
            if "VERSION" in str(url):
                return _FakeResp(200, text="3.2.2\n")
            return _FakeResp(200, json_data={"tag_name": "v3.2.2"})

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="3.2.2"
        ):
            await check_github_update(force=False)

        version_calls = [c for c in calls if "VERSION" in c["url"]]
        self.assertTrue(version_calls)
        self.assertIsInstance(version_calls[0]["params"], dict)
        self.assertIn("_", version_calls[0]["params"])


if __name__ == "__main__":
    unittest.main()
