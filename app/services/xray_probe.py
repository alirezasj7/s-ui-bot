"""Run one isolated, verified Xray client for a bounded endpoint batch."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.services.connection_monitor_config import MonitorBinding
from app.services.connection_monitor_types import MonitorEndpoint
from app.services.xray_probe_process import (
    drain_output,
    finish_cleanup,
    spawn_process,
    stop_process,
    verify_version,
    wait_ready,
)
from app.services.xray_probe_resources import ProbeResources, XrayBinary, XrayProbeError, prepare_resources


BIND_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class XrayBatch:
    bindings: tuple[MonitorBinding, ...]
    process: asyncio.subprocess.Process

    @property
    def is_alive(self) -> bool:
        return self.process.returncode is None


async def _prepare(endpoints: tuple[MonitorEndpoint, ...]) -> ProbeResources:
    task = asyncio.create_task(asyncio.to_thread(prepare_resources, endpoints))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await finish_cleanup(_close_pending_resources(task))
        raise
    except OSError:
        raise XrayProbeError("core_resources") from None


async def _close_pending_resources(task: asyncio.Task[ProbeResources]) -> None:
    resources = await task
    await asyncio.to_thread(resources.close)


@asynccontextmanager
async def _attempt(path: str, endpoints: tuple[MonitorEndpoint, ...]) -> AsyncIterator[XrayBatch]:
    resources = await _prepare(endpoints)
    process = None
    reader = None
    try:
        resources.release_ports()
        process = await spawn_process(path, "run", "-config", str(resources.config_path))
        ready = asyncio.Event()
        reader = asyncio.create_task(drain_output(process, ready))
        await wait_ready(process, ready)
        yield XrayBatch(resources.bindings, process)
    finally:
        await finish_cleanup(_close_attempt(resources, process, reader))


async def _close_attempt(resources: ProbeResources, process: asyncio.subprocess.Process | None,
                         reader: asyncio.Task[None] | None) -> None:
    try:
        if process is not None:
            await stop_process(process)
    finally:
        if reader is not None:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        await asyncio.to_thread(resources.close)


@asynccontextmanager
async def run_xray_batch(binary: XrayBinary, endpoints: tuple[MonitorEndpoint, ...]) -> AsyncIterator[XrayBatch]:
    path = str(await asyncio.to_thread(binary.verify))
    await verify_version(path)
    for attempt in range(BIND_ATTEMPTS):
        manager = _attempt(path, endpoints)
        try:
            batch = await manager.__aenter__()
        except XrayProbeError:
            if attempt + 1 == BIND_ATTEMPTS:
                raise
        else:
            try:
                yield batch
            finally:
                await manager.__aexit__(None, None, None)
            return
