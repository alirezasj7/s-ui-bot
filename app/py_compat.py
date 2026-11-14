"""Python 3.11 standard-library pieces the panel uses, with stand-ins for Python 3.10.

Servers installed with Ubuntu 22.04 run the panel on Python 3.10, and the in-panel updater of
older versions keeps that interpreter, so the code must import and run there. On 3.11+ the
real standard-library objects are used unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import Awaitable, Iterable
from enum import Enum
from types import TracebackType
from typing import Any, BinaryIO, TypeVar

T = TypeVar("T")

if sys.version_info >= (3, 11):
    from asyncio import timeout
    from enum import StrEnum
    from hashlib import file_digest
else:

    class StrEnum(str, Enum):
        """``enum.StrEnum``: members are strings and print as their value."""

        def __str__(self) -> str:
            return str(self.value)

        def __format__(self, spec: str) -> str:
            return format(str(self.value), spec)

        @staticmethod
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:
            return name.lower()

    class _Timeout:
        """``asyncio.timeout``: cancel the block after ``delay`` seconds and raise TimeoutError."""

        def __init__(self, delay: float | None) -> None:
            self._delay = delay
            self._handle: asyncio.TimerHandle | None = None
            self._task: asyncio.Task[Any] | None = None
            self._expired = False

        async def __aenter__(self) -> _Timeout:
            self._task = asyncio.current_task()
            if self._delay is not None and self._task is not None:
                loop = asyncio.get_running_loop()
                self._handle = loop.call_later(max(float(self._delay), 0.0), self._expire)
            return self

        def _expire(self) -> None:
            self._expired = True
            if self._task is not None:
                self._task.cancel()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            if self._handle is not None:
                self._handle.cancel()
            if self._expired and exc_type is asyncio.CancelledError:
                # The builtin, like 3.11, so ``except TimeoutError`` keeps working.
                raise TimeoutError from exc
            return False

    def timeout(delay: float | None) -> _Timeout:
        return _Timeout(delay)

    def file_digest(fileobj: BinaryIO, digest: str) -> Any:
        """``hashlib.file_digest`` for a binary file opened for reading."""
        hasher = hashlib.new(digest)
        for chunk in iter(lambda: fileobj.read(1 << 16), b""):
            hasher.update(chunk)
        return hasher


async def gather_or_cancel(awaitables: Iterable[Awaitable[T]]) -> list[T]:
    """Run concurrently; on the first failure cancel the rest and re-raise it (TaskGroup-like)."""
    tasks = [asyncio.ensure_future(item) for item in awaitables]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


__all__ = ["StrEnum", "file_digest", "gather_or_cancel", "timeout"]
