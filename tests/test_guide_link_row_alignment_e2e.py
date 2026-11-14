"""REAL browser E2E: the remove circle of a guide video link sits level with the link field."""

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
<html lang="fa" dir="rtl"><head><meta charset="utf-8" /><link rel="stylesheet" href="/static/panel.css" /></head>
<body><div class="card"><fieldset class="full guides-links"><legend>لینک ویدیو</legend>
<div class="guides-link-row" data-guides-link>
<label>متن دکمه<input type="text" class="guides-link-label" /></label>
<label>لینک<input type="url" class="guides-link-url" dir="ltr" /></label>
<button type="button" class="icon-btn icon-remove guides-link-remove" aria-label="حذف"><svg class="ico" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>
</div></fieldset></div></body></html>"""


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


class GuideLinkRowAlignmentE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    def test_the_remove_circle_is_level_with_the_url_field_on_phone_and_desktop(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as playwright:
                browser = _launch(playwright)
                for width in (390, 900):
                    with self.subTest(width=width):
                        page = browser.new_page(viewport={"width": width, "height": 600})
                        page.goto(f"http://127.0.0.1:{server.port}/", wait_until="networkidle")
                        field = page.locator(".guides-link-url").bounding_box()
                        button = page.locator(".guides-link-remove").bounding_box()
                        field_center = field["y"] + field["height"] / 2
                        button_center = button["y"] + button["height"] / 2
                        self.assertAlmostEqual(field_center, button_center, delta=1.0)
                        page.close()
                browser.close()
        finally:
            server.stop()
