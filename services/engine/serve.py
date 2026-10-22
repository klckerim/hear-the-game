"""Deployed server: static client + one replay session per WebSocket listener, on a single port.

    python -m services.engine.serve --seed 7 --port 8000

GET /         -> web/live.html     GET /healthz -> ok     WS /ws?chapter=first_goal -> messages as in `run_local`.
Each listener gets its own pipeline and replay clock, starting at the chosen chapter (unknown or missing -> the default);
the Director mode and favourite club are set per listener with `set_mode` and `set_favourite`.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from htg import telemetry
from htg.adapters.local import FileEventSource
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from services.engine.resolve import is_stale
from services.engine.run_local import LivePipeline, apply_listener_message, make_resolver, warm_up

CLIENT = Path(__file__).resolve().parents[2] / "web" / "live.html"
MAX_SESSIONS = 20
END_AFTER_S = 15 * 60.0  # a demo session lasts at most this much match time
# Demo start points in match minutes, for seed 7 (goals at 22:38, 79:11 and 87:14): nobody should wait 9 minutes for a goal.
CHAPTERS = {"kickoff": 0.0, "first_goal": 19.0, "late": 76.0}
DEFAULT_CHAPTER = "first_goal"
_warm: dict[tuple, LivePipeline] = {}
_warm_lock = threading.Lock()  # a thread lock: callers wait in their worker thread, never on the event loop


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


def chapter_of(path: str) -> str:
    """`/ws?chapter=late` -> "late"; a missing or unknown chapter -> the default."""
    chapter = parse_qs(urlsplit(path).query).get("chapter", [""])[0]
    return chapter if chapter in CHAPTERS else DEFAULT_CHAPTER


def warmed(meta: dict, match_dir: Path, start_minute: float, speed: float) -> LivePipeline:
    """Every listener of a chapter replays the same match from the same minute, so the warm-up is computed once and each session
    gets a copy.

    Measured on the deployed app: 10 listeners connecting together each ran their own warm-up and starved the event loop
    (`hello` p50 12.9 s, a 15.8 s stall in `state`). A copy takes about 1 ms.
    """
    key = (str(match_dir), start_minute, speed)
    with _warm_lock:
        if key not in _warm:
            pipe = LivePipeline(meta, "casual", speed)
            warm_up(pipe, match_dir, start_minute)
            _warm[key] = pipe
        return copy.deepcopy(_warm[key])


async def session(ws, match_dir: Path, meta: dict, start_minute: float, speed: float, sessions: set) -> None:
    if len(sessions) >= MAX_SESSIONS:
        await ws.close(1013, "busy")
        return
    sessions.add(ws)
    telemetry.sessions_active.add(1)
    resolver = await asyncio.to_thread(make_resolver, meta)  # Azure clients are built here; keep that off the loop too
    pipe: LivePipeline | None = None
    prefs: list[dict] = []  # set_mode / set_favourite received before the warmed pipeline exists
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
            if isinstance(msg, dict):
                prefs.append(msg)
                if pipe:
                    apply_listener_message(pipe, msg)

    async def deliver(msg: dict) -> None:
        final = await resolver.resolve(msg, insights[msg["insight_id"]])
        if is_stale(final, now):
            telemetry.dropped_stale.add(1)
        else:
            await send(final)

    async def play() -> None:
        nonlocal now, pipe
        warm = await asyncio.to_thread(warmed, meta, match_dir, start_minute, speed)  # off the loop; computed once per chapter
        for msg in prefs:
            apply_listener_message(warm, msg)
        pipe = warm
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


async def main(seed: int, speed: float, host: str, port: int) -> None:
    load_env()
    telemetry.setup()
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    meta = json.loads((match_dir / "meta.json").read_text())
    sessions: set = set()
    for minute in CHAPTERS.values():  # before the first listener arrives
        await asyncio.to_thread(warmed, meta, match_dir, minute, speed)

    async def handler(ws) -> None:  # noqa: ANN001
        await session(ws, match_dir, meta, CHAPTERS[chapter_of(ws.request.path)], speed, sessions)

    async with websockets.serve(handler, host, port, process_request=process_request, ping_interval=20):
        print(f"serving seed {seed}, chapters {CHAPTERS}, on {host}:{port} (HTG_ENV={os.environ.get('HTG_ENV', 'local')})")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=int(os.environ.get("HTG_SEED", 7)))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container entrypoint
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    a = ap.parse_args()
    try:
        asyncio.run(main(a.seed, a.speed, a.host, a.port))
    except KeyboardInterrupt:
        pass
