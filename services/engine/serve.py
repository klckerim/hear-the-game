"""Deployed server: static client + one replay session per WebSocket listener, on a single port.

    python -m services.engine.serve --seed 7 --start-minute 13 --port 8000

GET /         -> web/live.html     GET /healthz -> ok     WS /ws -> messages as in `run_local`.
Each listener gets its own pipeline and replay clock; the Director mode is set per listener with `set_mode`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from http import HTTPStatus
from pathlib import Path

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from htg import telemetry
from htg.adapters.local import FileEventSource
from htg.engine.director import SILENCE_S
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from services.engine.resolve import is_stale
from services.engine.run_local import LivePipeline, make_resolver, warm_up

CLIENT = Path(__file__).resolve().parents[2] / "web" / "live.html"
MAX_SESSIONS = 20
END_AFTER_S = 15 * 60.0  # a demo session lasts at most this much match time


def http_response(status: HTTPStatus, body: bytes, content_type: str) -> Response:
    headers = Headers({"Content-Type": content_type, "Content-Length": str(len(body)), "Cache-Control": "no-cache"})
    return Response(status.value, status.phrase, headers, body)


def process_request(connection, request):  # noqa: ANN001 - websockets hook; returning None lets the WebSocket handshake continue
    path = request.path.split("?")[0]
    if path == "/ws":
        return None
    if path == "/healthz":
        return http_response(HTTPStatus.OK, b"ok", "text/plain")
    if path in ("/", "/index.html"):
        return http_response(HTTPStatus.OK, CLIENT.read_bytes(), "text/html; charset=utf-8")
    return http_response(HTTPStatus.NOT_FOUND, b"not found", "text/plain")


async def session(ws, match_dir: Path, meta: dict, start_minute: float, speed: float, sessions: set) -> None:
    if len(sessions) >= MAX_SESSIONS:
        await ws.close(1013, "busy")
        return
    sessions.add(ws)
    telemetry.sessions_active.add(1)
    pipe, resolver = LivePipeline(meta, "casual", speed), make_resolver(meta)
    insights: dict[str, dict] = {}
    tasks: set[asyncio.Task] = set()
    now = start_minute * 60.0

    async def send(msg: dict) -> None:
        await ws.send(json.dumps(msg, separators=(",", ":")))

    async def listen() -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "set_mode" and msg.get("mode") in SILENCE_S:
                pipe.mode = msg["mode"]

    async def deliver(msg: dict) -> None:
        final = await resolver.resolve(msg, insights[msg["insight_id"]])
        if is_stale(final, now):
            telemetry.dropped_stale.add(1)
        else:
            await send(final)

    async def play() -> None:
        nonlocal now
        await asyncio.to_thread(warm_up, pipe, match_dir, start_minute)  # CPU-bound; keep the other listeners' loop free
        await send(pipe.hello())
        async for item in FileEventSource(match_dir, speed, start_minute):
            now = item.t
            if now - start_minute * 60.0 > END_AFTER_S:
                break
            for msg in pipe.feed(item):
                if msg["type"] == "speech":
                    task = asyncio.create_task(deliver(msg))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    continue
                if msg["type"] == "insight":
                    insights[msg["insight"]["insight_id"]] = msg["insight"]
                await send(msg)
        await asyncio.gather(*tasks, return_exceptions=True)

    runner = asyncio.gather(listen(), play())
    try:
        await runner
    except websockets.ConnectionClosed:
        pass
    finally:
        runner.cancel()
        for t in tasks:
            t.cancel()
        sessions.discard(ws)
        telemetry.sessions_active.add(-1)


async def main(seed: int, speed: float, start_minute: float, host: str, port: int) -> None:
    load_env()
    telemetry.setup()
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    meta = json.loads((match_dir / "meta.json").read_text())
    sessions: set = set()

    async def handler(ws) -> None:  # noqa: ANN001
        await session(ws, match_dir, meta, start_minute, speed, sessions)

    async with websockets.serve(handler, host, port, process_request=process_request, ping_interval=20):
        print(f"serving seed {seed} from minute {start_minute} on {host}:{port} (HTG_ENV={os.environ.get('HTG_ENV', 'local')})")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=int(os.environ.get("HTG_SEED", 7)))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--start-minute", type=float, default=float(os.environ.get("HTG_START_MINUTE", 13)))
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container entrypoint
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    a = ap.parse_args()
    try:
        asyncio.run(main(a.seed, a.speed, a.start_minute, a.host, a.port))
    except KeyboardInterrupt:
        pass
