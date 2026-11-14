"""Safe internal redirect helpers for panel POST next= params."""

from __future__ import annotations

_SAFE_NEXT_PREFIXES: tuple[str, ...] = (
    "/finance",
    "/tickets",
    "/loyalty",
    "/message-variables",
    "/shop-settings",
    "/settings",
    "/home",
    "/dashboard",
    "/security",
    "/users",
    "/resellers",
    "/plans",
    "/gift-codes",
    "/broadcast",
)


def safe_internal_next(raw: str | None, fallback: str) -> str:
    """Return an internal relative URL or fallback.

    Blocks open redirects, scheme-relative URLs, control characters, and
    destinations outside the panel allowlist.
    """
    value = (raw or "").strip()
    if not value:
        return fallback
    if not value.startswith("/") or value.startswith("//") or "://" in value:
        return fallback
    if "\\" in value or any(ord(ch) < 32 for ch in value):
        return fallback
    path = value.split("?", 1)[0].split("#", 1)[0]
    if not any(path == prefix or path.startswith(prefix + "/") for prefix in _SAFE_NEXT_PREFIXES):
        return fallback
    return value
