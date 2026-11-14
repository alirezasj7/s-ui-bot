"""Short timeouts for *display-only* probes — never used for allow/deny.

Auth gates, ACL, tenant resolution, and PG client selection must NOT call this.
On timeout/failure returns the provided fallback (typically unchecked payloads).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, TypeVar

logger = logging.getLogger(__name__)

# Decorative UI probes only (connection badges, overview widgets).
DISPLAY_PROBE_TIMEOUT_SEC = 3.0

T = TypeVar("T")


async def display_await(
    awaitable: Awaitable[T],
    *,
    fallback: T,
    label: str = "display",
) -> T:
    """Wait briefly for a decorative coroutine; never elevates permissions."""
    try:
        return await asyncio.wait_for(awaitable, timeout=DISPLAY_PROBE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.info("display probe timeout label=%s limit=%ss", label, DISPLAY_PROBE_TIMEOUT_SEC)
        return fallback
    except Exception:
        logger.exception("display probe failed label=%s", label)
        return fallback
