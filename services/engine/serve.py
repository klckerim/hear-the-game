"""Deployed server: static client + one replay session per WebSocket listener, on a single port.

    python -m services.engine.serve --seed 7 --port 8000

GET /         -> web/live.html     GET /healthz -> ok     WS /ws?chapter=first_goal -> messages as in `run_local`;
`hello` adds `window` [start, end] (match seconds the session plays, never past the end of the match).
GET /tour/tour.json, /tour/<step>_<lang>.mp3 -> the sound tour's text table and pre-generated voice lines.
GET /callouts/callouts.json, /callouts/<lang>_<tone>_<id>.mp3 -> the callout clip table and clips (`htg/speech/callouts.py`).
Each listener gets its own pipeline and replay clock, starting at the chosen chapter (unknown or missing -> the default);
the Director mode and favourite club are set per listener with `set_mode` and `set_favourite`.
{"type": "recap_request", "since_min": optional} -> a `recap` message ("What did I miss?"; default the last 10 minutes), and at the
end of period 2 the server sends a full-time `recap` by itself. Both come from the Recap agent (`htg/recap/agent.py`) with the
template recap as fallback, and never block the replay.
Every STATS_EVERY_S of match time a `stats` message carries `get_stats` (the recap agent's own tool) for the match so far
(`match`) and the last 10 minutes (`last10`): the Analyst table.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from htg import telemetry
from htg.adapters.base import Speech
from htg.adapters.local import FileEventSource
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import known_names, persona_for
from htg.recap.agent import AUDIO_DIR, RecapModel, get_recap_model
from htg.recap.tools import MatchRecord, get_stats
from services.engine.recap import recap_message, since_for
from services.engine.resolve import is_stale
from services.engine.run_local import LivePipeline, apply_listener_message, make_resolver, warm_up

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "web" / "live.html"
TOUR_TEXT = ROOT / "web" / "tour.json"
TOUR_AUDIO = ROOT / "data" / "cache" / "tour"
TOUR_CLIP = re.compile(r"/tour/([a-z_]+_(?:en|tr)\.mp3)")
CALLOUT_AUDIO = ROOT / "data" / "cache" / "callouts"
CALLOUT_FILE = re.compile(r"/callouts/((?:en|tr)_[a-z0-9_]+\.mp3|callouts\.json)")
# Home-screen icon (iOS asks for the PNG), favicon, and the manifest + icons Chrome needs for its install prompt
ICONS = {"/apple-touch-icon.png": "image/png", "/icon.svg": "image/svg+xml", "/icon-192.png": "image/png", "/icon-512.png": "image/png",
         "/manifest.webmanifest": "application/manifest+json"}
MAX_SESSIONS = 20
END_AFTER_S = 15 * 60.0  # a demo session lasts at most this much match time
STATS_EVERY_S = 10.0
# Demo start points in match minutes, for seed 7 (goals at 22:38, 79:11 and 87:14): nobody should wait 9 minutes for a goal.
CHAPTERS = {"kickoff": 0.0, "first_goal": 19.0, "late": 76.0}
DEFAULT_CHAPTER = "first_goal"
_warm: dict[tuple, LivePipeline] = {}
_warm_lock = threading.Lock()  # a thread lock: callers wait in their worker thread, never on the event loop
_records: dict[str, MatchRecord] = {}
_recap_model: RecapModel | None = None  # set in main(); None -> the template recap
_recap_speech: Speech | None = None  # Azure voice with the recap clip cache; None -> the session's (local: no audio)


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
    if path == "/tour/tour.json":
        return http_response(HTTPStatus.OK, TOUR_TEXT.read_bytes(), "application/json")
    if path in ICONS:
        return http_response(HTTPStatus.OK, (ROOT / "web" / path[1:]).read_bytes(), ICONS[path])
    if (m := TOUR_CLIP.fullmatch(path)) and (TOUR_AUDIO / m.group(1)).exists():
        return http_response(HTTPStatus.OK, (TOUR_AUDIO / m.group(1)).read_bytes(), "audio/mpeg")
    if (m := CALLOUT_FILE.fullmatch(path)) and (CALLOUT_AUDIO / m.group(1)).exists():
        kind = "application/json" if m.group(1).endswith(".json") else "audio/mpeg"
        return http_response(HTTPStatus.OK, (CALLOUT_AUDIO / m.group(1)).read_bytes(), kind)
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


def stats_message(rec: MatchRecord, t: float) -> dict:
    """Team stats up to `t`: the same deterministic numbers the recap agent sees, for the match and for the last 10 minutes."""
    return {"type": "stats", "t": t, "match": get_stats(rec, t), "last10": get_stats(rec, t, from_min=max(0.0, t / 60.0 - 10))}


def record_for(match_dir: Path) -> MatchRecord:
    """The recap tools' view of the match, loaded once per server."""
    with _warm_lock:
        if str(match_dir) not in _records:
            _records[str(match_dir)] = MatchRecord.load(match_dir)
        return _records[str(match_dir)]


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

    async def recap(kind: str, t: float, since_min: object = None) -> None:
        rec = await asyncio.to_thread(record_for, match_dir)
        fav, mode = (pipe.favourite, pipe.mode) if pipe else (None, "casual")
        speech = _recap_speech or resolver.speech
        await send(await recap_message(rec, _recap_model, speech, known_names(meta), t, kind, since_for(kind, t, since_min), fav,
                                       persona_for(mode)))

    def spawn(coro) -> None:  # noqa: ANN001
        task = asyncio.create_task(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def listen() -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "recap_request":
                spawn(recap("missed", now, msg.get("since_min")))
                continue
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
        end = min(start_minute * 60.0 + END_AFTER_S, meta.get("duration_s", float("inf")))  # Late drama ends at 90', not 91'
        await send({**pipe.hello(), "window": [start_minute * 60.0, end]})  # the session's match time
        rec, next_stats = await asyncio.to_thread(record_for, match_dir), 0.0
        async for item in FileEventSource(match_dir, speed, start_minute):
            now = item.t
            if now - start_minute * 60.0 > END_AFTER_S:
                break
            if now >= next_stats:
                next_stats = now + STATS_EVERY_S
                await send(stats_message(rec, now))
            if item.kind == "event" and item.data["type"] == "period_end" and item.data["period"] == 2:
                spawn(recap("full_time", item.t))
            for msg in pipe.feed(item):
                if msg["type"] == "speech":
                    spawn(deliver(msg))
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
    global _recap_model, _recap_speech
    await asyncio.to_thread(record_for, match_dir)
    _recap_model = await asyncio.to_thread(get_recap_model)
    if _recap_model is not None:
        try:
            from htg.speech.azure import AzureSpeech

            _recap_speech = AzureSpeech(cache_dir=AUDIO_DIR)
        except Exception as e:
            print(f"Recap voice unavailable ({type(e).__name__}); recaps use the session voice.")

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
