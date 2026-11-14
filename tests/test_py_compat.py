"""The Python 3.10 stand-ins behave like the 3.11 standard library they replace."""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import unittest

from app.py_compat import StrEnum, file_digest, gather_or_cancel, timeout


class Colour(StrEnum):
    RED = "red"
    DARK_BLUE = "dark_blue"


class StrEnumTests(unittest.TestCase):
    def test_members_are_their_string_value(self) -> None:
        self.assertEqual(Colour.RED, "red")
        self.assertEqual(str(Colour.RED), "red")
        self.assertEqual(f"{Colour.DARK_BLUE}", "dark_blue")
        self.assertIs(Colour("red"), Colour.RED)


class TimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_slow_block_raises_the_builtin_timeout_error(self) -> None:
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            async with timeout(0.05):
                await asyncio.sleep(5)
        self.assertLess(time.monotonic() - started, 1)

    async def test_a_fast_block_is_left_alone(self) -> None:
        async with timeout(1):
            await asyncio.sleep(0)
        await asyncio.sleep(0.02)  # a cancelled timer must not fire later

    async def test_no_delay_means_no_limit(self) -> None:
        async with timeout(None):
            await asyncio.sleep(0.01)

    async def test_other_errors_pass_through(self) -> None:
        with self.assertRaises(ValueError):
            async with timeout(1):
                raise ValueError("boom")


class GatherOrCancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_results_keep_their_order(self) -> None:
        async def value(n: int, delay: float) -> int:
            await asyncio.sleep(delay)
            return n

        self.assertEqual(await gather_or_cancel([value(1, 0.02), value(2, 0)]), [1, 2])

    async def test_a_failure_cancels_the_others_and_is_raised(self) -> None:
        cancelled = asyncio.Event()

        async def slow() -> None:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async def broken() -> None:
            await asyncio.sleep(0)
            raise RuntimeError("probe failed")

        with self.assertRaises(RuntimeError):
            await gather_or_cancel([slow(), broken()])
        self.assertTrue(cancelled.is_set())


class FileDigestTests(unittest.TestCase):
    def test_matches_hashlib(self) -> None:
        data = b"x" * 200_000
        self.assertEqual(file_digest(io.BytesIO(data), "sha256").hexdigest(), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
