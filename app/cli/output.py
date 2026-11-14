"""CLI output helpers — clear, non-noisy status lines."""

from __future__ import annotations

import sys
from typing import Any


class CliError(Exception):
    def __init__(self, message: str, *, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _stream(msg: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    stream.write(msg + "\n")
    stream.flush()


def info(msg: str) -> None:
    _stream(f"  · {msg}")


def ok(msg: str) -> None:
    _stream(f"  ✓ {msg}")


def warn(msg: str) -> None:
    _stream(f"  ! {msg}", err=True)


def err(msg: str) -> None:
    _stream(f"  ✗ {msg}", err=True)


def header(title: str) -> None:
    _stream("")
    _stream(f"PGClock · {title}")
    _stream("─" * (10 + len(title)))


def kv(key: str, value: Any) -> None:
    _stream(f"  {key:<16} {value}")
