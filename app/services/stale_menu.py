"""Throttle for the «menu updated» notice sent for unrecognised keyboard text."""

from __future__ import annotations

from datetime import datetime, timezone

STALE_NOTICE_WINDOW_SECONDS = 30.0


def should_send_stale_notice(
    last_sent_at: object, *, now: datetime | None = None
) -> bool:
    """True when no notice went out to this user within the throttle window.

    ``last_sent_at`` comes from FSM data and may be missing or malformed; both
    count as "never sent" so a bad value cannot silence the notice forever.
    """
    if isinstance(last_sent_at, bool) or not isinstance(last_sent_at, (int, float)):
        return True
    current = (now or datetime.now(timezone.utc)).timestamp()
    elapsed = current - float(last_sent_at)
    return elapsed < 0 or elapsed >= STALE_NOTICE_WINDOW_SECONDS
