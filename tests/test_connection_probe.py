"""Offline HTTPS result, resource, routing and total deadline behavior."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx

from app.services.connection_probe import (
    PROBE_DESTINATIONS,
    ProbeDestination,
    probe_client,
    probe_control,
    probe_proxy,
    request_destination,
)
from app.services.connection_status_types import ObservationKind


class UnreadBody(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise AssertionError("Monitoring must not download response bodies")
        yield b""  # An async iterator is required even though reading is forbidden.

    async def aclose(self) -> None:
        self.closed = True


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_proxy_transport_initializes_and_closes_without_sending_requests(self) -> None:
        client = await asyncio.to_thread(probe_client, port=18080)
        async with client:
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)

    async def test_204_is_success_without_reading_body_and_closes_stream(self) -> None:
        body = UnreadBody()
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204, stream=body)

        async with probe_client(port=18080, transport=httpx.MockTransport(handler)) as client:
            result = await probe_proxy(client, control_ok=False, account_valid=True, runner_alive=lambda: True)
        self.assertEqual(result.kind, ObservationKind.SUCCESS)
        self.assertEqual(result.destination, "gstatic")
        self.assertIsInstance(result.delay_ms, int)
        self.assertIsNotNone(result.checked_at.tzinfo)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[0].headers["Connection"], "close")
        self.assertTrue(body.closed)

    async def test_unexpected_statuses_redirects_and_errors_are_not_success(self) -> None:
        for status in (200, 301, 302, 403, 500):
            bodies = [UnreadBody(), UnreadBody()]
            requests: list[str] = []

            def handler(request: httpx.Request) -> httpx.Response:
                requests.append(str(request.url))
                return httpx.Response(status, headers={"Location": "https://untrusted.example"}, stream=bodies[len(requests)-1])

            with self.subTest(status=status):
                async with probe_client(port=18080, transport=httpx.MockTransport(handler)) as client:
                    result = await probe_proxy(client, control_ok=True, account_valid=True, runner_alive=lambda: True)
                self.assertEqual(result.kind, ObservationKind.FAILURE)
                self.assertIsNone(result.delay_ms)
                self.assertEqual(requests, [destination.url for destination in PROBE_DESTINATIONS])
                self.assertTrue(all(body.closed for body in bodies))

    async def test_second_destination_uses_the_same_client_after_first_failure(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if len(requested) == 1:
                raise httpx.ConnectError("sensitive TLS failure", request=request)
            return httpx.Response(204)

        async with probe_client(port=18080, transport=httpx.MockTransport(handler)) as client:
            result = await probe_proxy(client, control_ok=True, account_valid=True, runner_alive=lambda: True)
        self.assertEqual(result.kind, ObservationKind.SUCCESS)
        self.assertEqual(result.destination, "cloudflare")
        self.assertEqual(result.reason, "fallback_destination")
        self.assertEqual(len(requested), 2)

    async def test_shared_control_success_cannot_replace_failed_proxy_measurement(self) -> None:
        control = httpx.MockTransport(lambda request: httpx.Response(204))
        self.assertTrue(await probe_control(transport=control))
        for control_ok, expected in ((True, ObservationKind.FAILURE), (False, ObservationKind.UNKNOWN)):
            with self.subTest(control_ok=control_ok):
                transport = httpx.MockTransport(lambda request: httpx.Response(500))
                async with probe_client(port=18080, transport=transport) as client:
                    result = await probe_proxy(client, control_ok=control_ok, account_valid=True, runner_alive=lambda: True)
                self.assertEqual(result.kind, expected)
                self.assertIsNone(result.delay_ms)

    async def test_control_checks_fallback_only_after_failure(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(500 if len(requested) == 1 else 204)

        self.assertTrue(await probe_control(transport=httpx.MockTransport(handler)))
        self.assertEqual(requested, [destination.url for destination in PROBE_DESTINATIONS])

    async def test_total_deadline_bounds_slow_response_headers(self) -> None:
        async def slow(request: httpx.Request) -> httpx.Response:
            for _ in range(20):
                await asyncio.sleep(0.01)
            return httpx.Response(204)

        async with probe_client(port=18080, transport=httpx.MockTransport(slow)) as client:
            with patch("app.services.connection_probe.REQUEST_SECONDS", 0.025):
                result = await request_destination(client, PROBE_DESTINATIONS[0])
        self.assertEqual(result.reason, "request_timeout")
        self.assertIsNone(result.delay_ms)

    async def test_httpx_timeout_and_transport_error_do_not_leak_exception_text(self) -> None:
        for error in (httpx.ReadTimeout("sensitive token"), httpx.ConnectError("sensitive certificate")):
            def fail(request: httpx.Request) -> httpx.Response:
                raise error
            async with probe_client(port=18080, transport=httpx.MockTransport(fail)) as client:
                result = await request_destination(client, PROBE_DESTINATIONS[0])
            self.assertNotIn("sensitive", repr(result))
            self.assertIsNone(result.delay_ms)

    async def test_invalid_account_and_dead_core_never_create_requests(self) -> None:
        def unexpected(request: httpx.Request) -> httpx.Response:
            raise AssertionError("No request should be sent")

        async with probe_client(port=18080, transport=httpx.MockTransport(unexpected)) as client:
            account = await probe_proxy(client, control_ok=True, account_valid=False, runner_alive=lambda: True)
            core = await probe_proxy(client, control_ok=True, account_valid=True, runner_alive=lambda: False)
        self.assertEqual(account.kind, ObservationKind.NOT_READY)
        self.assertEqual(core.kind, ObservationKind.UNKNOWN)

    async def test_core_exit_after_204_invalidates_the_success(self) -> None:
        alive = True

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal alive
            alive = False
            return httpx.Response(204)

        async with probe_client(port=18080, transport=httpx.MockTransport(handler)) as client:
            result = await probe_proxy(client, control_ok=True, account_valid=True, runner_alive=lambda: alive)
        self.assertEqual(result.kind, ObservationKind.UNKNOWN)
        self.assertEqual(result.reason, "core_unavailable")
        self.assertIsNone(result.delay_ms)

    async def test_client_explicitly_configures_loopback_tls_timeouts_and_no_retries(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(204))
        with patch("app.services.connection_probe.httpx.AsyncHTTPTransport", return_value=transport) as factory:
            async with probe_client(port=18081) as client:
                self.assertFalse(client.follow_redirects)
                self.assertEqual(client.timeout.connect, 5)
            kwargs = factory.call_args.kwargs
        self.assertEqual(kwargs["proxy"], "http://127.0.0.1:18081")
        self.assertTrue(kwargs["verify"])
        self.assertFalse(kwargs["trust_env"])
        self.assertFalse(kwargs["http2"])
        self.assertEqual(kwargs["retries"], 0)
        self.assertEqual(kwargs["limits"].max_keepalive_connections, 0)

    async def test_only_fixed_destinations_and_strict_loopback_ports_are_allowed(self) -> None:
        for port in (True, -1, 0, 65536, "18080", 18080.0):
            with self.subTest(port=port), self.assertRaises(ValueError):
                probe_client(port=port)
        async with probe_client(port=18080, transport=httpx.MockTransport(lambda request: httpx.Response(204))) as client:
            with self.assertRaises(ValueError):
                await request_destination(client, ProbeDestination("attacker", "http://127.0.0.1/private"))

    async def test_cancellation_propagates_without_becoming_a_host_failure(self) -> None:
        requested = asyncio.Event()

        async def slow(request: httpx.Request) -> httpx.Response:
            requested.set()
            await asyncio.Event().wait()
            return httpx.Response(204)

        async with probe_client(port=18080, transport=httpx.MockTransport(slow)) as client:
            task = asyncio.create_task(probe_proxy(client, control_ok=True, account_valid=True, runner_alive=lambda: True))
            await requested.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
