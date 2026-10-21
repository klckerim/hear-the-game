"""Local adapters: replay from files, broadcast over a local WebSocket server."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.server import Server, ServerConnection

from htg.replay import Item, replay


class FileEventSource:
    def __init__(self, match_dir: Path, speed: float = 1.0, start_minute: float = 0):
        self.match_dir, self.speed, self.start_minute = Path(match_dir), speed, start_minute

    def __aiter__(self) -> AsyncIterator[Item]:
        return replay(self.match_dir, self.speed, self.start_minute)


class WebSocketBroadcaster:
    """Pushes every message to all connected clients. Listeners only receive; anything they send is ignored."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host, self.port = host, port
        self._clients: set[ServerConnection] = set()
        self._server: Server | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]  # real port when started with port=0

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            self._clients.discard(ws)

    async def publish(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        payload = json.dumps(message, separators=(",", ":"))
        await asyncio.gather(*(c.send(payload) for c in list(self._clients)), return_exceptions=True)
