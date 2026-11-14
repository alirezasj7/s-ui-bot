"""Which settings a keyboard button's text and color come from.

The keyboard helpers note a source for every button they create while a
``recording_button_sources()`` block is active; outside one they skip the work
after a single context-variable read, so menus are built exactly as before.
Inside one, the screen editor builds the real menu and reads the setting keys
behind each button in order, so the editor can never list a button the menu
does not show or miss one it does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ButtonSource:
    """``label_key``: btn_* setting holding the text, None when the text is fixed in code.
    ``style_id``: button-style catalog id holding the color, None when the color is fixed.
    """

    label_key: str | None
    style_id: str | None

    @property
    def is_editable(self) -> bool:
        return self.label_key is not None or self.style_id is not None


class ButtonSourceLog:
    """Sources noted while recording, matched to buttons by object identity."""

    def __init__(self) -> None:
        self._entries: list[tuple[object, ButtonSource]] = []

    def note(self, button: object, source: ButtonSource) -> None:
        self._entries.append((button, source))

    def source_of(self, button: object) -> ButtonSource | None:
        for noted, source in self._entries:
            if noted is button:
                return source
        return None


_active_log: ContextVar[ButtonSourceLog | None] = ContextVar("button_source_log", default=None)


@contextmanager
def recording_button_sources() -> Iterator[ButtonSourceLog]:
    log = ButtonSourceLog()
    token = _active_log.set(log)
    try:
        yield log
    finally:
        _active_log.reset(token)


def is_recording() -> bool:
    return _active_log.get() is not None


def note_button_source(button: object, *, label_key: str | None, style_id: str | None) -> None:
    log = _active_log.get()
    if log is not None:
        log.note(button, ButtonSource(label_key=label_key, style_id=style_id))
