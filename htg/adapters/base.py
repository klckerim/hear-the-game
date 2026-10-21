"""Adapter contracts. Local implementations live in `local.py`; Azure ones would sit next to them."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from htg.replay import Item


class EventSource(Protocol):
    """Timed match items (ball frames, events, physical rows) in replay order."""

    def __aiter__(self) -> AsyncIterator[Item]: ...


class Broadcaster(Protocol):
    """Sends one JSON-serialisable message to every connected listener."""

    async def publish(self, message: dict[str, Any]) -> None: ...
