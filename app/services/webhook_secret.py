"""Persist Telegram webhook secret token (required when WEBHOOK_URL is set)."""

from __future__ import annotations

import secrets

from app.config import DATA_DIR, get_settings

SECRET_FILE = DATA_DIR / "webhook_secret.token"


def ensure_webhook_secret() -> str:
    settings = get_settings()
    env_secret = (settings.webhook_secret_token or "").strip()
    if env_secret:
        return env_secret
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        existing = SECRET_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(32)
    SECRET_FILE.write_text(token + "\n", encoding="utf-8")
    try:
        SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return token
