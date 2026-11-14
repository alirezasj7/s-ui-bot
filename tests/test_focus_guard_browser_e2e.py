"""REAL browser E2E: a guarded input never opens the keyboard on load but works for real taps and keys."""

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
<html lang="fa" dir="rtl"><head><meta charset="utf-8" /><title>focus guard</title></head>
<body>
  <button type="button" id="before">قبلی</button>
  <form><label for="u">نام کاربری</label>
    <input id="u" name="username" data-focus-guard required autocomplete="off" /></form>
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


class FocusGuardBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    def _page(self, playwright, server):
        browser = _launch(playwright)
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{server.port}/", wait_until="networkidle")
        return browser, page

    def test_load_time_focus_is_dropped_and_the_keyboard_stays_closed(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as p:
                browser, page = self._page(p, server)
                page.evaluate("document.getElementById('u').focus()")
                page.wait_for_timeout(200)
                self.assertEqual(page.evaluate("document.activeElement.id"), "")
                self.assertTrue(page.evaluate("document.getElementById('u').readOnly"))
                browser.close()
        finally:
            server.stop()

    def test_a_real_click_unlocks_the_field_for_typing(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as p:
                browser, page = self._page(p, server)
                page.click("#u")
                page.keyboard.type("MattDev")
                self.assertEqual(page.input_value("#u"), "MattDev")
                self.assertFalse(page.evaluate("document.getElementById('u').readOnly"))
                browser.close()
        finally:
            server.stop()

    def test_keyboard_users_can_tab_into_the_field_and_type(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as p:
                browser, page = self._page(p, server)
                page.focus("#before")
                page.keyboard.press("Tab")
                page.keyboard.type("abc")
                self.assertEqual(page.input_value("#u"), "abc")
                browser.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
