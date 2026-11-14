"""REAL browser E2E: setting an enhanced select from script is what the form submits (add-on pack kind bug)."""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from tests.test_delete_reason_browser_e2e import _free_port, _launch

ROOT = Path(__file__).resolve().parents[1]

PAGE = """<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8" /><title>select</title></head>
<body>
  <form id="f" method="post" action="/x">
    <select name="kind" id="kind" required>
      <option value="volume">حجم (گیگ)</option>
      <option value="duration">زمان (روز)</option>
    </select>
  </form>
  <script src="/static/panel.js"></script>
</body></html>"""


class _Server:
    def __init__(self) -> None:
        self.port = _free_port()
        app = FastAPI()
        app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "web" / "static")), name="static")

        @app.get("/")
        async def home() -> HTMLResponse:
            return HTMLResponse(PAGE)

        self._server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


def submitted_kind(page) -> str:
    return page.evaluate("new FormData(document.getElementById('f')).get('kind')")


class UiSelectProgrammaticValueE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    def _open(self, playwright, server):
        browser = _launch(playwright)
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{server.port}/", wait_until="networkidle")
        return browser, page

    def test_a_value_set_from_script_is_submitted_and_shown(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as playwright:
                browser, page = self._open(playwright, server)
                self.assertEqual(submitted_kind(page), "volume")
                page.evaluate("document.getElementById('kind').value = 'duration'")
                self.assertEqual(submitted_kind(page), "duration")
                self.assertIn("زمان", page.locator(".ui-select-label").inner_text())
                page.evaluate("document.getElementById('kind').value = 'volume'")
                self.assertEqual(submitted_kind(page), "volume")
                browser.close()
        finally:
            server.stop()
