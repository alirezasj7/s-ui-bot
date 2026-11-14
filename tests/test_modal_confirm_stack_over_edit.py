"""Root fix: confirm must stack ABOVE user-edit when deleting from the edit modal.

Regression for the v10.1.14 failure:
  open edit → body-append after #modal-confirm → same z-index 4000 →
  confirm paints underneath → reason unreachable →
  flash «علت حذف کاربر الزامی است (حداقل ۳ کاراکتر)».
"""

from __future__ import annotations

import json
import os
import shutil
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/panel.js"
CSS = ROOT / "app/web/static/panel.css"
USER_EDIT = ROOT / "app/web/templates/_user_edit_body.html"
USERS = ROOT / "app/web/templates/users.html"
BASE = ROOT / "app/web/templates/base.html"


def _fn_src(js: str, name: str) -> str:
    key = f"function {name}("
    start = js.find(key)
    if start < 0:
        raise AssertionError(f"missing {name}")
    i = js.find("{", start)
    depth = 0
    for j in range(i, len(js)):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start : j + 1]
    raise AssertionError(f"unbalanced {name}")


def _jsdom_available() -> bool:
    node = shutil.which("node")
    if node is None:
        return False
    env = {**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/tmp/jsdom-deps/node_modules")}
    probe = subprocess.run(
        [node, "-e", "require('jsdom')"], cwd="/tmp", capture_output=True, check=False, env=env, timeout=30
    )
    return probe.returncode == 0


JSDOM_SKIP_REASON = "node with the jsdom package (NODE_PATH or /tmp/jsdom-deps/node_modules) is required"


def _run_node(script: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "proof.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(path)],
            cwd="/tmp",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/tmp/jsdom-deps/node_modules")},
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr or proc.stdout or "node failed")
        return json.loads(proc.stdout)


class ModalConfirmStackStaticTests(unittest.TestCase):
    def test_bring_to_front_wired_into_open_modal(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("function bringModalToFront(", js)
        self.assertIn("function topOpenModal(", js)
        open_fn = js.split("function openModal(", 1)[1].split("window.openModal", 1)[0]
        self.assertIn("bringModalToFront(el, opts)", open_fn)
        self.assertIn("opts.stack", open_fn)
        bring = _fn_src(js, "bringModalToFront")
        self.assertIn("document.body.appendChild(el)", bring)
        self.assertIn("4600", bring)
        # Re-append even when already on body — the actual root bug.
        self.assertIn("el.parentNode === document.body", bring)

    def test_panel_confirm_uses_stack_true(self):
        js = JS.read_text(encoding="utf-8")
        start = js.find("window.panelConfirm = function")
        self.assertGreater(start, 0)
        block = js[start : start + 2000]
        self.assertIn("openModal('modal-confirm', { stack: true })", block)

    def test_finish_close_clears_front_zindex(self):
        finish = _fn_src(JS.read_text(encoding="utf-8"), "finishCloseModal")
        self.assertIn("is-front", finish)
        self.assertIn("el.style.zIndex = ''", finish)

    def test_escape_uses_top_open_modal(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("const open = topOpenModal()", js)
        self.assertNotIn(
            "document.querySelectorAll('.ui-modal.open').forEach(closeModal)",
            js,
        )

    def test_css_confirm_floor_above_edit(self):
        css = CSS.read_text(encoding="utf-8")
        base = re.search(r"(?ms)^\.ui-modal\s*\{([^}]+)\}", css)
        self.assertIsNotNone(base)
        self.assertIn("z-index: 4000", base.group(1))
        self.assertIn("#modal-confirm", css)
        self.assertIn("z-index: 4600", css)

    def test_delete_from_user_edit_still_requires_reason(self):
        html = USER_EDIT.read_text(encoding="utf-8")
        delete = html.split('action="/users/{{ user.id }}/delete"', 1)[1].split(
            "</form>", 1
        )[0]
        self.assertIn('data-confirm-reason="1"', delete)
        self.assertIn('name="reason"', delete)
        users = USERS.read_text(encoding="utf-8")
        self.assertIn('id="modal-user-edit"', users)
        base = BASE.read_text(encoding="utf-8")
        self.assertIn('id="modal-confirm"', base)
        self.assertLess(
            base.find('id="modal-confirm"'),
            base.find('src="/static/panel.js'),
        )


@unittest.skipUnless(_jsdom_available(), JSDOM_SKIP_REASON)
class ModalConfirmStackRuntimeProof(unittest.TestCase):
    """jsdom runtime using REAL bringModalToFront / topOpenModal from panel.js."""

    def test_pre_fix_same_zindex_edit_paints_last(self):
        """Old failure: without re-append+raise, later edit stays on top."""
        payload = _run_node(
            textwrap.dedent(
                """
                const { JSDOM } = require('jsdom');
                const dom = new JSDOM(`<!doctype html><html><body>
                  <div class="ui-modal" id="modal-confirm" style="z-index:4000"></div>
                  <div id="page"><div class="ui-modal" id="modal-user-edit" style="z-index:4000"></div></div>
                </body></html>`);
                const { document } = dom.window;
                const confirm = document.getElementById('modal-confirm');
                const edit = document.getElementById('modal-user-edit');
                if (edit.parentNode !== document.body) document.body.appendChild(edit);
                if (confirm.parentNode !== document.body) document.body.appendChild(confirm);
                const editLast = document.body.lastElementChild === edit;
                const sameZ = edit.style.zIndex === confirm.style.zIndex;
                process.stdout.write(JSON.stringify({ editLast, sameZ, broken: editLast && sameZ }));
                """
            )
        )
        self.assertTrue(payload["broken"], payload)

    def test_stacked_confirm_above_prior_edit_modal(self):
        js_src = JS.read_text(encoding="utf-8")
        top = _fn_src(js_src, "topOpenModal")
        bring = _fn_src(js_src, "bringModalToFront")
        # Production helpers call ensureModalPorted — stub it for the harness.
        script = (
            textwrap.dedent(
                """
                const { JSDOM } = require('jsdom');
                const dom = new JSDOM(`<!doctype html><html><body>
                  <div class="ui-modal" id="modal-confirm" hidden><div class="ui-modal-panel">c</div></div>
                  <div id="page">
                    <div class="ui-modal" id="modal-user-edit" hidden><div class="ui-modal-panel">e</div></div>
                  </div>
                </body></html>`, { url: 'https://example.test/users' });
                const { window } = dom;
                const { document } = window;
                document.querySelectorAll('.ui-modal').forEach((el) => {
                  if (!el.style.zIndex) el.style.zIndex = '4000';
                });
                const modalHomes = new WeakMap();
                function ensureModalPorted(el){
                  if (!el) return;
                  if (!modalHomes.has(el)) {
                    modalHomes.set(el, { parent: el.parentNode, next: el.nextSibling });
                  }
                  if (el.parentNode !== document.body) document.body.appendChild(el);
                }
                """
            )
            + top
            + "\n"
            + bring
            + textwrap.dedent(
                """
                function openModal(id, opts){
                  opts = opts || {};
                  const el = document.getElementById(id);
                  if (!el) return;
                  const stack = !!opts.stack;
                  if (!stack) {
                    document.querySelectorAll('.ui-modal.open').forEach((m) => {
                      if (m !== el) {
                        m.classList.remove('open', 'is-front', 'is-stack');
                        m.hidden = true;
                        m.style.zIndex = '4000';
                      }
                    });
                  } else {
                    el.classList.add('is-stack');
                  }
                  el.hidden = false;
                  el.classList.add('open');
                  bringModalToFront(el, opts);
                }
                openModal('modal-user-edit');
                openModal('modal-confirm', { stack: true });
                const edit = document.getElementById('modal-user-edit');
                const confirm = document.getElementById('modal-confirm');
                const ez = parseInt(edit.style.zIndex, 10);
                const cz = parseInt(confirm.style.zIndex, 10);
                const confirmAfter = !!(edit.compareDocumentPosition(confirm) & 4);
                const out = {
                  ez, cz, confirmAfter,
                  confirmFront: confirm.classList.contains('is-front'),
                  bothOpen: edit.classList.contains('open') && confirm.classList.contains('open'),
                };
                out.ok = out.bothOpen && cz > ez && confirmAfter && out.confirmFront;
                process.stdout.write(JSON.stringify(out));
                """
            )
        )
        payload = _run_node(script)
        self.assertTrue(payload.get("ok"), payload)
        self.assertGreater(payload["cz"], payload["ez"])
        self.assertGreaterEqual(payload["cz"], 4600)
        self.assertTrue(payload["confirmAfter"])


if __name__ == "__main__":
    unittest.main()
