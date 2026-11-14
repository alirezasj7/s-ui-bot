"""Small HTTPS requests over explicit loopback proxies and shared direct controls."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.py_compat import timeout as async_timeout
from app.services.connection_status_types import ObservationKind, ProbeObservation

REQUEST_SECONDS = 5


@dataclass(frozen=True, slots=True)
class ProbeDestination:
    key: str
    url: str


PROBE_DESTINATIONS = (
    ProbeDestination("gstatic", "https://www.gstatic.com/generate_204"),
    ProbeDestination("cloudflare", "https://cp.cloudflare.com/generate_204"),
)


@dataclass(frozen=True, slots=True)
class ProbeAttempt:
    destination: str
    delay_ms: int | None = None
    reason: str | None = None


def probe_client(*, port: int | None, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    if port is not None and (type(port) is not int or not 1024 <= port <= 65535):
        raise ValueError("Invalid loopback probe port")
    proxy = f"http://127.0.0.1:{port}" if port is not None else None
    # A test transport replaces the complete network boundary, including proxy I/O.
    network = transport or httpx.AsyncHTTPTransport(
        proxy=proxy, verify=True, trust_env=False, http2=False, retries=0,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )
    return httpx.AsyncClient(
        transport=network, trust_env=False, follow_redirects=False, http2=False,
        timeout=httpx.Timeout(REQUEST_SECONDS), headers={"Connection": "close", "User-Agent": "PGClockBot/connection-monitor"},
    )


async def request_destination(client: httpx.AsyncClient, destination: ProbeDestination) -> ProbeAttempt:
    if destination not in PROBE_DESTINATIONS:
        raise ValueError("Unsupported monitoring destination")
    started = time.monotonic()
    try:
        async with async_timeout(REQUEST_SECONDS):
            async with client.stream("GET", destination.url) as response:
                if response.status_code != 204:
                    return ProbeAttempt(destination.key, reason="unexpected_status")
        elapsed = time.monotonic() - started
        if elapsed >= REQUEST_SECONDS:
            return ProbeAttempt(destination.key, reason="request_timeout")
        return ProbeAttempt(destination.key, delay_ms=max(0, round(elapsed * 1000)))
    except (TimeoutError, httpx.TimeoutException):
        return ProbeAttempt(destination.key, reason="request_timeout")
    except httpx.HTTPError:
        return ProbeAttempt(destination.key, reason="transport_error")


async def probe_control(*, transport: httpx.AsyncBaseTransport | None = None) -> bool:
    client = await asyncio.to_thread(probe_client, port=None, transport=transport)
    async with client:
        for destination in PROBE_DESTINATIONS:
            if (await request_destination(client, destination)).delay_ms is not None:
                return True
    return False


async def probe_proxy(client: httpx.AsyncClient, *, control_ok: bool, account_valid: bool,
                      runner_alive: Callable[[], bool]) -> ProbeObservation:
    if not account_valid:
        return ProbeObservation(ObservationKind.NOT_READY, datetime.now(timezone.utc), reason="account_unavailable")
    for index, destination in enumerate(PROBE_DESTINATIONS):
        if not runner_alive():
            return ProbeObservation(ObservationKind.UNKNOWN, datetime.now(timezone.utc), reason="core_unavailable")
        attempt = await request_destination(client, destination)
        if attempt.delay_ms is not None and runner_alive():
            return ProbeObservation(
                ObservationKind.SUCCESS, datetime.now(timezone.utc), attempt.destination, attempt.delay_ms,
                reason="fallback_destination" if index else None,
            )
    if not runner_alive():
        reason = "core_unavailable"
    elif not control_ok:
        reason = "control_unavailable"
    else:
        reason = "proxy_failed"
    kind = ObservationKind.FAILURE if reason == "proxy_failed" else ObservationKind.UNKNOWN
    return ProbeObservation(kind, datetime.now(timezone.utc), reason=reason)
