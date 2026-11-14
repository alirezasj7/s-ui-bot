"""REAL browser E2E: delete reason must reach the server from a display:none kebab.

Playwright drives Chromium against a live ASGI server that uses the same
``extract_delete_reason`` / ``delete_reason_too_short`` gate as production.
The delete form sits inside a display:none ops menu — the mobile failure mode
that previously dropped the reason field on native form.submit().
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.services.delete_reason import delete_reason_too_short, extract_delete_reason  # noqa: F401 — names verified below

ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = ROOT / "app" / "web" / "static" / "panel.js"


def _launch(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception:  # noqa: BLE001 - playwright raises a generic Error for a missing browser
        builds = sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
        if not builds:
            raise
        return playwright.chromium.launch(headless=True, executable_path=str(builds[-1]))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


PAGE = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="csrf-token" content="e2e-csrf-token" />
  <title>E2E delete reason</title>
  <style>
    .row-actions-menu:not(.is-open) {
      display: none !important;
      width: 0; height: 0; overflow: hidden;
    }
    .ui-modal[hidden], .ui-modal:not(.open) { display: none !important; }
    .ui-modal.open { display: block !important; position: fixed; inset: 0;
      background: rgba(0,0,0,.35); z-index: 9999; }
    .ui-modal-panel { background: #fff; margin: 10vh auto; padding: 1rem; max-width: 28rem; }
    textarea, button { font-size: 16px; }
    .flash.err { color: #b00020; background: #fdecea; padding: .75rem; }
    .flash.ok { color: #0b6b2d; background: #e8f7ee; padding: .75rem; }
  </style>
</head>
<body>
  <h1>کاربران</h1>
  <div id="flash"></div>

  <div class="row-actions">
    <button type="button" id="open-ops">عملیات</button>
    <div class="row-actions-menu" id="ops-menu">
      <form id="del" method="post" action="/users/7/delete"
            data-confirm="کاربر و داده‌های مرتبط حذف شوند؟"
            data-confirm-title="تأیید حذف کاربر"
            data-confirm-danger="1"
            data-confirm-reason="1"
            data-confirm-reason-label="علت حذف"
            data-confirm-reason-name="reason"
            data-confirm-label="حذف کاربر">
        <input type="hidden" name="csrf_token" value="e2e-csrf-token" />
        <input type="hidden" name="reason" value="" />
        <button type="submit" id="delete-btn">حذف</button>
      </form>
    </div>
  </div>

  <div class="ui-modal" id="modal-confirm" hidden>
    <div class="ui-modal-backdrop" data-modal-close></div>
    <div class="ui-modal-panel" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div class="ui-modal-head">
        <h2 id="confirm-title">تأیید</h2>
        <button type="button" data-modal-close aria-label="بستن">×</button>
      </div>
      <form id="confirm-form" class="form-stack" action="#" method="post" data-panel-validate="0" novalidate>
        <input type="hidden" name="csrf_token" value="e2e-csrf-token" />
        <p id="confirm-message" class="confirm-message"></p>
        <div id="confirm-reason-slot" hidden></div>
        <div class="actions">
          <button type="submit" class="btn btn-danger" id="confirm-submit">تأیید</button>
          <button type="button" class="btn btn-ghost" data-modal-close>انصراف</button>
        </div>
      </form>
    </div>
  </div>

  <script>
    document.getElementById('open-ops').addEventListener('click', function () {
      document.getElementById('ops-menu').classList.add('is-open');
    });
  </script>
  <script src="/static/panel.js"></script>
  <script>
    /* After panel.js: production closeRowActions() hides the kebab while
       confirm runs. Mimic that by closing ops as soon as confirm opens, so
       the originating form is display:none during the reason POST. */
    (function () {
      var menu = document.getElementById('ops-menu');
      var modal = document.getElementById('modal-confirm');
      function hideOps() {
        if (menu) menu.classList.remove('is-open');
      }
      if (window.panelConfirm) {
        var orig = window.panelConfirm;
        window.panelConfirm = function (opts) {
          hideOps();
          return orig(opts);
        };
      }
      if (modal && typeof MutationObserver === 'function') {
        new MutationObserver(function () {
          if (modal.classList.contains('open')) hideOps();
        }).observe(modal, { attributes: true, attributeFilter: ['class'] });
      }
    })();
  </script>
</body>
</html>
"""


class _Server:
    def __init__(self) -> None:
        self.port = _free_port()
        self.received: list[dict] = []
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

        app = FastAPI()
        static_dir = ROOT / "app" / "web" / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def home():
            return HTMLResponse(PAGE)

        @app.get("/users")
        async def users(request: Request):
            err = request.query_params.get("err") or ""
            ok = request.query_params.get("ok") or ""
            flash = ""
            if err:
                flash = f'<div class="flash err" id="flash-err">{err}</div>'
            if ok:
                flash = f'<div class="flash ok" id="flash-ok">{ok}</div>'
            return HTMLResponse(
                PAGE.replace('<div id="flash"></div>', f'<div id="flash">{flash}</div>')
            )

        @app.post("/users/{user_id}/delete")
        async def users_delete(request: Request, user_id: int):
            form = await request.form()
            reason = extract_delete_reason(form)
            self.received.append(
                {
                    "user_id": user_id,
                    "reason": reason,
                    "content_type": request.headers.get("content-type", ""),
                    "keys": list(form.keys()),
                }
            )
            if delete_reason_too_short(reason):
                return RedirectResponse(
                    url="/users?err=" + "علت حذف کاربر الزامی است (حداقل ۳ کاراکتر)",
                    status_code=303,
                )
            return RedirectResponse(url="/users?ok=deleted", status_code=303)

        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

    def start(self) -> None:
        assert self._server is not None

        def run() -> None:
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("e2e server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


@unittest.skipUnless(PANEL_JS.is_file(), "panel.js missing")
class DeleteReasonBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"playwright not installed: {exc}") from exc

    def test_reason_survives_display_none_kebab_and_deletes(self) -> None:
        from playwright.sync_api import sync_playwright

        reason = "تخلف تکرار شده"
        server = _Server()
        server.start()
        try:
            with sync_playwright() as p:
                browser = _launch(p)
                page = browser.new_page()
                posts: list[dict] = []

                def on_request(req) -> None:
                    if req.method == "POST" and "/users/7/delete" in req.url:
                        posts.append(
                            {
                                "url": req.url,
                                "post_data": req.post_data or "",
                                "headers": dict(req.headers),
                            }
                        )

                page.on("request", on_request)
                page.goto(f"http://127.0.0.1:{server.port}/", wait_until="networkidle")

                # Prove panel.js loaded and confirm helper exists
                ready = page.evaluate("typeof window.panelConfirm")
                self.assertEqual(ready, "function", "panel.js did not expose panelConfirm")

                page.click("#open-ops")
                self.assertTrue(page.locator("#ops-menu").is_visible())
                page.click("#delete-btn")

                # Kebab must close (display:none) while confirm is open
                page.wait_for_selector("#confirm-reason", timeout=8000)
                page.wait_for_function(
                    "() => !document.getElementById('ops-menu').classList.contains('is-open')",
                    timeout=5000,
                )
                hidden = page.evaluate(
                    """() => {
                      const m = document.getElementById('ops-menu');
                      const cs = getComputedStyle(m);
                      return cs.display === 'none';
                    }"""
                )
                self.assertTrue(hidden, "ops menu must be display:none during confirm/POST")

                page.fill("#confirm-reason", reason)
                page.click("#confirm-submit")

                page.wait_for_url("**/users?ok=deleted*", timeout=10000)
                self.assertGreaterEqual(page.locator("#flash-ok").count(), 1)
                self.assertEqual(page.locator("#flash-err").count(), 0)
                browser.close()

            self.assertTrue(posts, "browser never POSTed /users/7/delete")
            raw = posts[0]["post_data"]
            parsed = parse_qs(raw, keep_blank_values=True)
            got = (parsed.get("reason") or []) + (parsed.get("confirm_reason") or [])
            self.assertIn(reason, got, parsed)
            self.assertTrue(server.received, "server never handled delete")
            self.assertEqual(server.received[0]["reason"], reason)
            self.assertIn(
                "application/x-www-form-urlencoded",
                posts[0]["headers"].get("content-type", ""),
            )
        finally:
            server.stop()

    def test_short_reason_blocked_client_side(self) -> None:
        from playwright.sync_api import sync_playwright

        server = _Server()
        server.start()
        try:
            with sync_playwright() as p:
                browser = _launch(p)
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.port}/", wait_until="networkidle")
                page.click("#open-ops")
                page.click("#delete-btn")
                page.wait_for_selector("#confirm-reason", timeout=8000)
                page.fill("#confirm-reason", "اب")
                page.click("#confirm-submit")
                page.wait_for_timeout(500)
                # Still on same page; no successful redirect
                self.assertNotIn("ok=deleted", page.url)
                self.assertEqual(server.received, [])
                browser.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
