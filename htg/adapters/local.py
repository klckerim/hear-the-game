"""Local adapters: replay from files, broadcast over a local WebSocket server."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.server import Server, ServerConnection

from htg.narration.templates import narrate
from htg.replay import Item, replay


class FileEventSource:
    def __init__(self, match_dir: Path, speed: float = 1.0, start_minute: float = 0, lead_s: float = 0.0):
        self.match_dir, self.speed, self.start_minute, self.lead_s = Path(match_dir), speed, start_minute, lead_s

    def __aiter__(self) -> AsyncIterator[Item]:
        return replay(self.match_dir, self.speed, self.start_minute, self.lead_s)


class WebSocketBroadcaster:
    """Pushes every message to all connected clients. Listeners only receive; what they send goes to `on_message` (if set)."""

    def __init__(self, host: str = "localhost", port: int = 8765, on_message: Callable[[dict], None] | None = None):
        self.host, self.port, self.on_message = host, port, on_message
        self._clients: set[ServerConnection] = set()
        self._server: Server | None = None
        self._connected = asyncio.Event()

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]  # real port when started with port=0

    async def wait_for_client(self) -> None:
        await self._connected.wait()

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        self._connected.set()
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if self.on_message and isinstance(msg, dict):
                    self.on_message(msg)
        finally:
            self._clients.discard(ws)

    async def publish(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        payload = json.dumps(message, separators=(",", ":"))
        await asyncio.gather(*(c.send(payload) for c in list(self._clients)), return_exceptions=True)


class TemplateNarrator:
    """Local narrator: the deterministic template sentence, no model. One template set serves both personas."""

    name = "template"

    def write(self, insight: dict, feedback: dict[str, list[str]] | None = None, persona: str = "fan") -> dict[str, Any]:
        return {"en": narrate(insight, "en"), "tr": narrate(insight, "tr"), "used_facts": sorted(insight["claim_facts"])}


class NoSpeech:
    def synthesize(self, text: str, lang: str, goal: bool = False) -> bytes | None:
        return None
