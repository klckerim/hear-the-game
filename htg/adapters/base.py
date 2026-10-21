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


class Narrator(Protocol):
    """Writes one sentence per language for an Insight. `name` identifies the writer in cache keys."""

    name: str

    def write(self, insight: dict, feedback: dict[str, list[str]] | None = None) -> dict[str, Any]:
        """Returns {"en": str, "tr": str, "used_facts": [str]}. `feedback` maps a language to Verifier reasons for a retry."""
        ...


class Speech(Protocol):
    """Text to audio. Returns MP3 bytes, or None when no voice is available (the client then falls back to speechSynthesis)."""

    def synthesize(self, text: str, lang: str, goal: bool = False) -> bytes | None: ...
