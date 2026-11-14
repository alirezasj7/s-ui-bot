from __future__ import annotations

import json
import secrets
from pathlib import Path

from passlib.context import CryptContext

from app.config import DATA_DIR

AUTH_FILE = DATA_DIR / "web_admin.json"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_BCRYPT_PREFIXES = ("$2b$", "$2a$", "$2y$")


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clean_secret(value: str | None) -> str:
    # Fix broken installs that stored leading/trailing newlines in .env / JSON
    return (value or "").replace("\r", "").strip()


def _is_bcrypt_hash(value: str) -> bool:
    return bool(value) and value.startswith(_BCRYPT_PREFIXES)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def validate_password_strength(
    password: str,
    *,
    username: str | None = None,
) -> tuple[bool, str]:
    """Delegate to Phase D1 shared policy (PasarGuard-aligned)."""
    from app.services.credential_policy import validate_password_strength as _v

    return _v(password, username=username)


def save_web_admin(username: str, password: str) -> Path:
    """Persist web panel credentials in a dedicated JSON file (not fragile .env).

    Password is stored as a bcrypt hash. If the value already looks like bcrypt,
    it is kept as-is (avoids re-hashing hashes on repair paths).
    """
    _ensure_data_dir()
    username = _clean_secret(username) or "admin"
    password = _clean_secret(password)
    if not username or not password:
        raise ValueError("username and password are required")
    stored = password if _is_bcrypt_hash(password) else hash_password(password)
    payload = {
        "username": username,
        "password": stored,
        "token": secrets.token_hex(16),
    }
    AUTH_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass
    return AUTH_FILE


def load_web_admin() -> dict[str, str]:
    _ensure_data_dir()
    if AUTH_FILE.exists():
        try:
            raw = AUTH_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            # Corrupt file must never 500 login / session checks — fail closed.
            import logging

            logging.getLogger(__name__).exception(
                "web_admin.json unreadable; treating as unset credentials"
            )
            return {"username": "admin", "password": "", "token": ""}
        if not isinstance(data, dict):
            return {"username": "admin", "password": "", "token": ""}
        username = _clean_secret(str(data.get("username", "admin")))
        password = _clean_secret(str(data.get("password", "")))
        token = _clean_secret(str(data.get("token", "")))
        # Auto-repair dirty credentials written by older installs
        if password and (
            str(data.get("password", "")) != password
            or str(data.get("username", "")).strip() != username
            or not token
            or not _is_bcrypt_hash(password)
        ):
            try:
                save_web_admin(username, password)
                data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
                username = _clean_secret(str(data.get("username", "admin")))
                password = _clean_secret(str(data.get("password", "")))
                token = _clean_secret(str(data.get("token", "")))
            except Exception:
                import logging

                logging.getLogger(__name__).exception("web_admin auto-repair failed")
                return {"username": username or "admin", "password": "", "token": ""}
        return {"username": username or "admin", "password": password, "token": token}

    # Fallback for old installs: migrate from .env once (never import example placeholders)
    from app.config import get_settings
    from app.services.security_policy import is_placeholder_password

    get_settings.cache_clear()
    settings = get_settings()
    user = _clean_secret(settings.web_admin_user) or "admin"
    password = _clean_secret(settings.web_admin_password)
    if password and not is_placeholder_password(password):
        try:
            save_web_admin(user, password)
            return load_web_admin()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("web_admin migrate-from-env failed")
            return {"username": user, "password": "", "token": ""}
    return {"username": "admin", "password": "", "token": ""}


def admin_session_version() -> str:
    """Opaque value that changes whenever admin credentials are rewritten."""
    try:
        return (load_web_admin().get("token") or "").strip()
    except Exception:
        return ""


def verify_web_admin(username: str, password: str) -> bool:
    creds = load_web_admin()
    u = _clean_secret(username)
    p = _clean_secret(password)
    expected_u = creds.get("username") or ""
    expected_p = creds.get("password") or ""
    if not expected_u or not expected_p:
        return False
    try:
        user_ok = secrets.compare_digest(u.encode("utf-8"), expected_u.encode("utf-8"))
    except ValueError:
        return False
    if not user_ok:
        return False

    if _is_bcrypt_hash(expected_p):
        try:
            return pwd_context.verify(p, expected_p)
        except (ValueError, TypeError):
            return False

    # Legacy plaintext — upgrade to bcrypt on successful login
    try:
        pass_ok = secrets.compare_digest(p.encode("utf-8"), expected_p.encode("utf-8"))
    except ValueError:
        return False
    if pass_ok:
        save_web_admin(expected_u, p)
    return pass_ok


def verify_password_hash(password: str, password_hash: str | None) -> bool:
    if not password or not password_hash:
        return False
    try:
        return pwd_context.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def change_web_admin_username(new_username: str) -> str:
    """Rename panel admin; keeps existing password hash. Returns cleaned username."""
    creds = load_web_admin()
    password = creds.get("password") or ""
    if not password:
        raise ValueError("رمز ادمین تنظیم نشده؛ ابتدا از ویزارد یا ترمینال رمز بگذارید")
    username = _clean_secret(new_username)
    if len(username) < 3:
        raise ValueError("نام کاربری حداقل ۳ کاراکتر باشد")
    save_web_admin(username, password)
    return username


def change_web_admin_password(new_password: str) -> None:
    creds = load_web_admin()
    username = creds.get("username") or "admin"
    ok, err = validate_password_strength(new_password)
    if not ok:
        raise ValueError(err)
    save_web_admin(username, new_password)


def validate_web_username(username: str, *, lowercase: bool = False) -> tuple[str, str | None]:
    """Return (cleaned_username, error_or_None).

    Aligned with PasarGuard ``UserValidator.validate_username`` so web logins
    that sync to PG admins never accept a username PG would reject.
    """
    from app.services.credential_policy import validate_pg_username

    return validate_pg_username(_clean_secret(username), lowercase=lowercase)


def repair_web_admin_from_env() -> dict[str, str]:
    """Migrate credentials from .env only when web_admin.json is missing/incomplete.

    Never overwrites an existing panel password or rotates the session token just
    because WEB_ADMIN_PASSWORD is still present in .env.
    """
    if AUTH_FILE.exists():
        data = load_web_admin()
        if data.get("password") and data.get("token"):
            return data

    from app.config import get_settings
    from app.services.security_policy import is_placeholder_password

    get_settings.cache_clear()
    settings = get_settings()
    user = _clean_secret(settings.web_admin_user) or "admin"
    password = _clean_secret(settings.web_admin_password)
    if not password or is_placeholder_password(password):
        return load_web_admin()
    save_web_admin(user, password)
    return load_web_admin()
