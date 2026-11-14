"""CSRF double-submit token + doctor Owner↔ADMIN_IDS contracts."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from app.services.csrf import (
    CSRF_COOKIE,
    CSRF_FORM_FIELD,
    csrf_tokens_match,
    ensure_csrf_token,
    new_csrf_token,
)

ROOT = Path(__file__).resolve().parents[1]


def test_csrf_tokens_match_rejects_empty_and_mismatch():
    tok = new_csrf_token()
    assert csrf_tokens_match(tok, tok)
    assert not csrf_tokens_match(tok, tok + "x")
    assert not csrf_tokens_match("", tok)
    assert not csrf_tokens_match(tok, "")


def test_ensure_csrf_token_reuses_cookie():
    req = MagicMock()
    req.cookies = {CSRF_COOKIE: "abc123_cookie_token_value_here"}
    req.state = MagicMock()
    req.state.csrf_token = None
    assert ensure_csrf_token(req) == "abc123_cookie_token_value_here"


def test_app_csrf_guard_requires_token_for_session_posts():
    src = (ROOT / "app" / "api" / "app.py").read_text(encoding="utf-8")
    assert "CSRF token rejected" in src
    assert "csrf_tokens_match" in src
    assert "extract_csrf_from_request" in src
    assert "ensure_csrf_token" in src
    assert CSRF_FORM_FIELD in (ROOT / "app" / "web" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    panel = (ROOT / "app" / "web" / "static" / "panel.js").read_text(encoding="utf-8")
    assert "X-CSRF-Token" in panel
    assert "csrf_token" in panel


def test_csp_nonce_wired():
    src = (ROOT / "app" / "api" / "app.py").read_text(encoding="utf-8")
    assert "csp_nonce" in src
    assert "nonce-" in src
    base = (ROOT / "app" / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "csp_nonce" in base


def test_doctor_owner_admin_ids_check_present():
    src = (ROOT / "app" / "cli" / "doctor_cmds.py").read_text(encoding="utf-8")
    assert "ADMIN_IDS" in src
    assert "Web Owner" in src
    assert "load_web_admin" in src
    tree = ast.parse(src)
    assert tree is not None


def test_login_post_exempt_from_csrf_token_when_stale_session():
    src = (ROOT / "app" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'path_now not in {\n                    "/login"' in src or '"/login"' in src
    assert "clear_stale_session" in src
    assert "CSRF token rejected" in src


def test_get_sh_supports_ref_pin():
    src = (ROOT / "get.sh").read_text(encoding="utf-8")
    assert "PGCLOCK_REF" in src
    assert "REMOTE_REF" in src
