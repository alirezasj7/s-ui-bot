"""Bounded subprocess startup signals and cancellation-safe child cleanup."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable
from typing import TypeVar

from app.py_compat import timeout as async_timeout
from app.services.xray_probe_resources import XRAY_VERSION, XrayProbeError

logger = logging.getLogger(__name__)
T = TypeVar("T")
CORE_START_SECONDS = 5
CORE_STOP_SECONDS = 2
READ_CHUNK_BYTES = 4096
START_MARKER = f"core: Xray {XRAY_VERSION} started".encode()


async def finish_cleanup(operation: Awaitable[T]) -> T:
    """Do not strand a child/file if cancellation arrives during cleanup itself."""
    task = asyncio.ensure_future(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            logger.debug("Probe child exited before termination")
        try:
            async with async_timeout(CORE_STOP_SECONDS):
                await process.wait()
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                logger.debug("Probe child exited before forced shutdown")
    async with async_timeout(CORE_STOP_SECONDS):
        await process.wait()


async def spawn_process(*arguments: str) -> asyncio.subprocess.Process:
    pending = asyncio.create_task(asyncio.create_subprocess_exec(
        *arguments, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, limit=READ_CHUNK_BYTES,
        env={"LANG": "C", "TZ": "UTC"}, start_new_session=True,
    ))
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        await finish_cleanup(_stop_pending(pending))
        raise
    except OSError:
        raise XrayProbeError("core_start") from None


async def _stop_pending(pending: asyncio.Task[asyncio.subprocess.Process]) -> None:
    process = await pending
    await stop_process(process)


async def drain_output(process: asyncio.subprocess.Process, ready: asyncio.Event) -> None:
    tail = b""
    while chunk := await process.stdout.read(READ_CHUNK_BYTES):
        combined = tail + chunk
        if re.search(rb"\[Warning\] " + re.escape(START_MARKER) + rb"\r?\n", combined):
            ready.set()
        # Output may contain credentials; retain only enough to match a split marker.
        tail = combined[-(len(START_MARKER) + 32):]


async def wait_ready(process: asyncio.subprocess.Process, ready: asyncio.Event) -> None:
    marker = asyncio.create_task(ready.wait())
    exited = asyncio.create_task(process.wait())
    try:
        async with async_timeout(CORE_START_SECONDS):
            await asyncio.wait((marker, exited), return_when=asyncio.FIRST_COMPLETED)
        if not ready.is_set() or process.returncode is not None:
            raise XrayProbeError("core_start")
    except TimeoutError:
        raise XrayProbeError("core_readiness") from None
    finally:
        for task in (marker, exited):
            task.cancel()
        await asyncio.gather(marker, exited, return_exceptions=True)


async def verify_version(path: str) -> None:
    process = await spawn_process(path, "version")
    try:
        async with async_timeout(CORE_START_SECONDS):
            output = await process.stdout.read(READ_CHUNK_BYTES)
            await process.wait()
        if process.returncode != 0 or not output.startswith(f"Xray {XRAY_VERSION} ".encode()):
            raise XrayProbeError("core_version")
    except TimeoutError:
        raise XrayProbeError("core_version") from None
    finally:
        await finish_cleanup(stop_process(process))
