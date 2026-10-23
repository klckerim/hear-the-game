"""Deployed server: static client + one replay session per WebSocket listener, on a single port.

    python -m services.engine.serve --port 8000

GET /         -> web/live.html     GET /healthz -> ok     GET /matches.json -> the fixture list (`htg/league.py`): per match its
id, seed, clubs, length, `moments` and Highlights `windows`, so the client can draw the timeline before a session starts.
WS /ws?match=<id>&mode=live&from=<seconds> -> messages as in `run_local`, from that match second to full time (`from` clamped to the
match; unknown match -> the default). WS /ws?match=<id>&mode=highlights[&from=] -> the moments back to back at 1x: each moment's
window [moment - 30 s, moment + 15 s] (overlapping windows merged); between windows a `cut` message {t_from, t_to, score} (score
from the server's warm-up), and the half-time and full-time recaps in between.
`hello` adds `match` (the fixture id), `watch` (live | highlights), `windows` [[start, end], ...] (match seconds the session
plays) and `moments` ({t, kind: goal|save|yellow|red, team} for every goal, saved shot and card).
GET /tour/tour.json, /tour/<step>_<lang>.mp3 -> the sound tour's text table and pre-generated voice lines.
GET /callouts/callouts.json, /callouts/<lang>_<tone>_<id>.mp3 -> the callout clip table and clips (`htg/speech/callouts.py`).
Each listener gets its own pipeline and replay clock; the Director mode and favourite club are set per listener with `set_mode` and
`set_favourite`.
{"type": "recap_request", "since_min": optional} -> a `recap` message ("What did I miss?"; default the last 10 minutes), and at the
end of period 2 the server sends a full-time `recap` by itself. Both come from the Recap agent (`htg/recap/agent.py`) with the
template recap as fallback, and never block the replay.
Broadcast delay: `&delay=20` (the fan modes) sends the first 20 s of match data at once and then stays 20 s ahead of what the
client plays, which is the budget of the live commentator: with COMMENTARY on (default under HTG_ENV=azure) every finished
segment of play becomes 0-2 verified `commentary` lines in the voice of `&lang=en|tr` (`services/engine/commentary.py`);
{"type": "set_lang", "lang": "tr"} switches that voice. `hello` adds `delay_s` and `commentary`. No delay (Analyst): no commentator.
Every STATS_EVERY_S of match time a `stats` message carries `get_stats` (the recap agent's own tool) for the match so far
(`match`) and the last 10 minutes (`last10`): the Analyst table.
A session ends when its socket closes; the client closes it when the tab has been hidden for 2 minutes.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from htg import telemetry
from htg.adapters.base import Speech
from htg.adapters.local import FileEventSource
from htg.commentary.commentator import Model, get_commentator
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.league import CLUBS, DEFAULT_MATCH, FIXTURES, fixture
from htg.narration.service import known_names, persona_for
from htg.recap.agent import AUDIO_DIR, RecapModel, get_recap_model
from htg.recap.tools import MatchRecord, get_stats
from services.engine.commentary import CommentaryStream
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
STATS_EVERY_S = 10.0
MAX_DELAY_S = 30.0
CLIP_BEFORE_S, CLIP_AFTER_S = 30.0, 15.0  # a Highlights window around each moment
HALF_S = 2700.0
WARM_MAX = 64  # warmed pipelines kept (~2 MB each; a start second per match); the least recently used goes first
_warm: OrderedDict[tuple, LivePipeline] = OrderedDict()
_warm_lock = threading.Lock()  # a thread lock: callers wait in their worker thread, never on the event loop
_records: dict[str, MatchRecord] = {}
_matches: dict[str, Match] = {}
_recap_model: RecapModel | None = None  # set in main(); None -> the template recap
_recap_speech: Speech | None = None  # Azure voice with the recap clip cache; None -> the session's (local: no audio)
_commentator: Model | None = None  # set in main(); None -> no live commentary


@dataclass
class Match:
    id: str
    dir: Path
    meta: dict
    moments: list[dict]

    @classmethod
    def load(cls, match_dir: Path, match_id: str | None = None) -> Match:
        meta = json.loads((match_dir / "meta.json").read_text())
        return cls(match_id or meta["match_id"], match_dir, meta, moments_of(record_for(match_dir).events))

    def info(self) -> dict:
        """One entry of /matches.json."""
        teams = {side: {"club": t.get("club"), "name_en": t["name"]["en"], "name_tr": t["name"]["tr"], "color": t["color"]}
                 for side, t in self.meta["teams"].items()}
        return {"id": self.id, "seed": self.meta["seed"], "teams": teams, "duration_s": self.meta["duration_s"], "moments": self.moments,
                "windows": highlight_windows(self.moments, self.meta["duration_s"])}


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
    if path == "/matches.json":
        body = {"default": DEFAULT_MATCH, "clubs": {k: {"name": c["name"], "color": c["color"]} for k, c in CLUBS.items()},
                "matches": [{**_matches[f["id"]].info(), "home": f["home"], "away": f["away"]} for f in FIXTURES if f["id"] in _matches]}
        return http_response(HTTPStatus.OK, json.dumps(body, ensure_ascii=False).encode(), "application/json")
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


def query(path: str, key: str, default: str = "") -> str:
    return parse_qs(urlsplit(path).query).get(key, [default])[0]


def delay_of(path: str) -> float:
    """`&delay=20` -> 20.0 (clamped to 0..MAX_DELAY_S); missing or bad -> 0 (Analyst: play at once)."""
    try:
        return min(max(float(query(path, "delay", "0")), 0.0), MAX_DELAY_S)
    except ValueError:
        return 0.0


def lang_of(path: str) -> str:
    return "tr" if query(path, "lang") == "tr" else "en"


def mode_of(path: str) -> str:
    return "highlights" if query(path, "mode") == "highlights" else "live"


def from_of(path: str, duration_s: float) -> float:
    """`&from=1345.6` -> 1345.0: whole seconds (the warm-up cache key), clamped to the match; missing or bad -> kick-off."""
    try:
        return float(min(max(int(float(query(path, "from", "0"))), 0), int(duration_s) - 1))
    except (ValueError, OverflowError):
        return 0.0


def moments_of(events: list[dict]) -> list[dict]:
    """The match's moments: goals (at the scoring shot), saved shots and cards, as {t, kind, team}."""
    out = []
    for e in events:
        if e["type"] == "shot" and e.get("outcome") in ("goal", "saved"):
            out.append({"t": e["t"], "kind": "goal" if e["outcome"] == "goal" else "save", "team": e["team"]})
        elif e.get("card"):
            out.append({"t": e["t"], "kind": e["card"], "team": e["team"]})
    return sorted(out, key=lambda m: m["t"])


def highlight_windows(moments: list[dict], duration_s: float) -> list[list[float]]:
    """[moment - 30 s, moment + 15 s] for every moment, clamped to the match; overlapping windows merged. Whole seconds."""
    out: list[list[float]] = []
    for m in moments:
        a, b = float(max(0, int(m["t"] - CLIP_BEFORE_S))), float(min(int(duration_s), int(m["t"] + CLIP_AFTER_S) + 1))
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def warmed(meta: dict, match_dir: Path, start_s: float, speed: float) -> LivePipeline:
    """Every listener who starts a match at the same second replays the same thing, so the warm-up is computed once and each
    session gets a copy.

    Measured on the deployed app: 10 listeners connecting together each ran their own warm-up and starved the event loop
    (`hello` p50 12.9 s, a 15.8 s stall in `state`). A copy takes about 8 ms.
    """
    key = (str(match_dir), start_s, speed)
    with _warm_lock:
        if key not in _warm:
            pipe = LivePipeline(meta, "casual", speed)
            warm_up(pipe, match_dir, start_s / 60.0)
            _warm[key] = pipe
            while len(_warm) > WARM_MAX:
                _warm.popitem(last=False)
        _warm.move_to_end(key)
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


async def session(ws, match: Match, windows: list[list[float]], speed: float, sessions: set, delay_s: float = 0.0, lang: str = "en",
                  commentator: Model | None = None, mode: str = "live") -> None:
    """Plays `windows` of the match in order: one window from the chosen second to full time (Live), or the Highlights clips."""
    if len(sessions) >= MAX_SESSIONS:
        await ws.close(1013, "busy")
        return
    sessions.add(ws)
    telemetry.sessions_active.add(1)
    meta, match_dir = match.meta, match.dir
    resolver = await asyncio.to_thread(make_resolver, meta)  # Azure clients are built here; keep that off the loop too
    pipe: LivePipeline | None = None
    prefs: list[dict] = []  # set_mode / set_favourite, applied again to the warmed copy of every window
    insights: dict[str, dict] = {}
    tasks: set[asyncio.Task] = set()
    now = windows[0][0]  # server match time: `delay_s` ahead of what the listener hears
    stream = CommentaryStream(commentator, resolver.speech, known_names(meta), meta.get("seed"), now / 60.0, delay_s, speed, lang,
                              lambda m: send(m), lambda: now) if commentator and delay_s > 0 else None
    sent_full_time = False

    async def send(msg: dict) -> None:
        await ws.send(json.dumps(msg, separators=(",", ":")))

    async def recap(kind: str, t: float, since_min: object = None, play_t: float | None = None) -> dict:
        rec = await asyncio.to_thread(record_for, match_dir)
        fav, persona_mode = (pipe.favourite, pipe.mode) if pipe else (None, "casual")
        speech = _recap_speech or resolver.speech
        msg = await recap_message(rec, _recap_model, speech, known_names(meta), t, kind, since_for(kind, t, since_min), fav,
                                  persona_for(persona_mode))
        if play_t is not None:  # Highlights: the recap plays where the listener is, not at 45:00 or 90:00
            msg["t"] = play_t
        await send(msg)
        return msg

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
                spawn(recap("missed", now - delay_s, msg.get("since_min")))  # what the listener has heard
                continue
            if msg.get("type") == "set_lang" and msg.get("lang") in ("en", "tr"):
                if stream:
                    stream.lang = msg["lang"]
                continue
            prefs.append(msg)
            if pipe:
                apply_listener_message(pipe, msg)

    async def deliver(msg: dict) -> None:
        final = await resolver.resolve(msg, insights[msg["insight_id"]])
        if is_stale(final, now - delay_s):
            telemetry.dropped_stale.add(1)
        else:
            await send(final)

    async def pause_for(msg: dict) -> None:
        """Highlights: wait while a recap plays (its clip length, else ~2.5 words a second for the device voice)."""
        clip = (msg.get("duration_s") or {}).get(stream.lang if stream else lang)
        await asyncio.sleep((clip or len(" ".join(msg["text"][lang]).split()) / 2.5) + 1.0)

    async def play() -> None:
        nonlocal now, pipe, sent_full_time
        rec, next_stats = await asyncio.to_thread(record_for, match_dir), 0.0
        for k, (t0, t1) in enumerate(windows):
            warm = await asyncio.to_thread(warmed, meta, match_dir, t0, speed)  # off the loop; computed once per start second
            for msg in prefs:
                apply_listener_message(warm, msg)
            if k == 0:
                pipe = warm
                await send({**pipe.hello(), "match": match.id, "watch": mode, "windows": windows, "moments": match.moments,
                            "delay_s": delay_s, "commentary": stream is not None})
                if stream:
                    spawn(stream.run())
            else:  # Highlights: the listener reaches the end of the clip, then the next one starts with its own delay buffer
                await asyncio.sleep(delay_s / speed)
                if windows[k - 1][1] <= HALF_S <= t0:
                    await pause_for(await recap("half_time", HALF_S, play_t=windows[k - 1][1]))
                pipe = warm
                await send({"type": "cut", "t_from": windows[k - 1][1], "t_to": t0, "score": pipe.detectors.score})
            async for item in FileEventSource(match_dir, speed, t0 / 60.0, delay_s):
                if item.t > t1:
                    break
                now = item.t
                if now >= next_stats:
                    next_stats = now + STATS_EVERY_S
                    await send(stats_message(rec, now))
                if item.kind == "event" and item.data["type"] == "period_end" and item.data["period"] == 2:
                    sent_full_time = True
                    spawn(recap("full_time", item.t))
                for msg in pipe.feed(item):
                    if msg["type"] == "speech":
                        spawn(deliver(msg))
                        continue
                    if msg["type"] == "segment":
                        if stream:
                            stream.push(msg["segment"])
                        continue
                    if msg["type"] == "insight":
                        insights[msg["insight"]["insight_id"]] = msg["insight"]
                    await send(msg)
        if mode == "highlights" and not sent_full_time:
            await asyncio.sleep(delay_s / speed)
            await recap("full_time", meta["duration_s"], play_t=windows[-1][1])  # same request, same cache as Live at 90:00
        if stream:
            stream.close()
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


def load_matches() -> dict[str, Match]:
    """Every fixture's match, generated on first use (under a second each) and kept on disk; a match on disk with other clubs is
    generated again (same events: club names never feed the RNG)."""
    out = {}
    for f in FIXTURES:
        match_dir = OUT_DIR / f"match_{f['seed']:04d}"
        try:
            teams = json.loads((match_dir / "meta.json").read_text())["teams"]
            fresh = [teams["HOME"].get("club"), teams["AWAY"].get("club")] == [f["home"], f["away"]]
        except (OSError, ValueError, KeyError):
            fresh = False
        if not fresh:
            match_dir = generate(f["seed"], home=f["home"], away=f["away"])
        out[f["id"]] = Match.load(match_dir, f["id"])
    return out


async def main(speed: float, host: str, port: int) -> None:
    load_env()
    telemetry.setup()
    _matches.update(await asyncio.to_thread(load_matches))
    sessions: set = set()
    default = _matches[DEFAULT_MATCH]
    await asyncio.to_thread(warmed, default.meta, default.dir, 0.0, speed)  # the first listener's start, before anyone arrives
    global _recap_model, _recap_speech, _commentator
    _recap_model = await asyncio.to_thread(get_recap_model)
    _commentator = await asyncio.to_thread(get_commentator)
    if _recap_model is not None:
        try:
            from htg.speech.azure import AzureSpeech

            _recap_speech = AzureSpeech(cache_dir=AUDIO_DIR)
        except Exception as e:
            print(f"Recap voice unavailable ({type(e).__name__}); recaps use the session voice.")

    async def handler(ws) -> None:  # noqa: ANN001
        path = ws.request.path
        match = _matches[fixture(query(path, "match"))["id"]]
        mode = mode_of(path)
        duration = match.meta["duration_s"]
        start = from_of(path, duration)
        # Highlights from `from`: the clips not yet over (a mode switch mid-Highlights picks up at the clip under way)
        windows = [w for w in highlight_windows(match.moments, duration) if w[1] > start] if mode == "highlights" else []
        if not windows:  # Live, or no clip left
            mode, windows = "live", [[start, duration]]
        await session(ws, match, windows, speed, sessions, delay_of(path), lang_of(path), _commentator, mode)

    async with websockets.serve(handler, host, port, process_request=process_request, ping_interval=20):
        print(f"serving {len(_matches)} matches ({', '.join(_matches)}) on {host}:{port}"
              f" (HTG_ENV={os.environ.get('HTG_ENV', 'local')}, commentary {_commentator.name if _commentator else 'off'})")
        if _commentator:
            from htg.speech.azure import commentary_voices

            primary, fallback = commentary_voices()
            print(f"commentary voices: {primary}, fallback {fallback}")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container entrypoint
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    a = ap.parse_args()
    try:
        asyncio.run(main(a.speed, a.host, a.port))
    except KeyboardInterrupt:
        pass
