"""Local live slice: replay -> state engine -> detectors -> Director -> WebSocket.

    python -m services.engine.run_local --seed 1 --speed 1 --start-minute 10

then open `web/live.html` (it connects to ws://localhost:8765). Replay starts when the first listener connects.
Listener -> server: {"type": "set_mode", "mode": "eyes_free" | "casual" | "analyst"} changes the Director's silence budget and the
narration persona (analyst for Analyst, fan otherwise); {"type": "set_favourite", "team": "HOME" | "AWAY" | null} gives that club's
Insights +1 priority in the Director.
Messages (JSON, one per WebSocket frame):
    hello      match info (teams with outfield players), score at the start, match length duration_s, replay speed, mode (first message)
    state      batch of 10 Hz state packets, every ~200 ms of match time
    event_cue  one sound cue (pass, shot, save, goal, whistle ..., period_end = half-time / full-time whistle), with the period;
               shots and goals add x, y (where the shot was taken; global frame, as the client draws it), events that have them add
               speed_mps and outcome, passes add length_m, restarts add restart (throw_in, corner, free_kick, goal_kick, keeper)
    insight    a detected Insight, its template text {en, tr}, evidence_points (one {seq, t, type, team, x, y} per evidence seq, max 30)
               and zone (flank overload: the flank band the detector counted, {x: [lo, hi], y: [lo, hi]} in the global frame; else null)
    speech     the Insight the Director decided to tell now: team, persona, text, source ("llm" verified / "template") and base64 MP3 audio
               per language, duration_s per language. Resolved in the background (cache first, 4 s deadline), never blocks the replay.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

from htg.adapters.local import FileEventSource, NoSpeech, TemplateNarrator, WebSocketBroadcaster
from htg.engine.detectors import Detectors, Params
from htg.engine.director import SILENCE_S, decide
from htg.engine.state import StateEngine
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import get_narrator, known_names, persona_for
from htg.narration.templates import narrate
from htg.pitch import LENGTH, WIDTH
from htg.replay import Item, iter_items
from services.engine.resolve import SpeechResolver, is_stale

BATCH_FRAMES = 2  # 10 Hz frames per `state` message = 200 ms
CUES = {"pass", "shot", "save", "goal", "out", "foul", "kickoff", "restart", "period_end"}
MAX_POINTS = 30  # evidence points per insight message


def evidence_zone(ins: dict, p: Params) -> dict | None:
    """The pitch area an Insight is about, in the global frame: the flank band the detector counted. Other Insights have no zone;
    their evidence points say enough. (Pressure has none: on seeds 1-10, 223 of 338 pressed actions were in the pressed team's
    attacking half and 115 in its own, so a "pressed team's half" shade would contradict its own dots.)"""
    if ins["type"] != "flank_overload":
        return None
    y0, y1 = (p.flank_high_y, WIDTH) if ins["claim_facts"]["side"] == "left" else (0.0, p.flank_low_y)  # attacking frame: left = high y
    if ins["team"] == "AWAY":  # AWAY's attacking frame is the global one mirrored
        y0, y1 = WIDTH - y1, WIDTH - y0
    return {"x": [0.0, LENGTH], "y": [y0, y1]}


class LivePipeline:
    """Feeds items in, returns the messages to broadcast. Pure bookkeeping, so `speed=inf` runs are reproducible."""

    def __init__(self, meta: dict, mode: str = "casual", speed: float = 1.0):
        self.meta, self.mode, self.speed = meta, mode, speed
        self.favourite: str | None = None  # "HOME" | "AWAY" | None
        self.engine, self.detectors = StateEngine.from_calibration(), Detectors(meta)
        self.queue: list[dict] = []
        self.spoken: list[tuple[float, str, str | None]] = []
        self._batch: list[dict] = []
        self._last_pan = 0.0
        self._points: dict[int, tuple] = {}  # seq -> (t, type, team, x, y, end x, end y) of every event with a position
        self._last_shot: dict[str, dict] = {}  # team -> its last shot, for the goal cue's position and speed

    def hello(self) -> dict:
        teams = {k: {"name_en": v["name"]["en"], "name_tr": v["name"]["tr"], "color": v["color"]} for k, v in self.meta["teams"].items()}
        for k, v in self.meta["teams"].items():
            teams[k]["players"] = [{"id": p["player_id"], "name": p["name"]} for p in v["players"] if p["role"] != "GK"]
        return {"type": "hello", "match_id": self.meta["match_id"], "seed": self.meta.get("seed"), "teams": teams, "mode": self.mode,
                "score": self.detectors.score, "duration_s": self.meta.get("duration_s"),
                "speed": self.speed if self.speed != float("inf") else 1.0}

    def feed(self, item: Item) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        packets = self.engine.step(item)
        if packets:
            self._last_pan = packets[-1]["pan"]
            self._batch += packets
        if item.kind == "event":
            self._remember(item.data)
            if item.data["type"] in CUES:
                out.append(self._cue(item.data))
        for ins in self.detectors.step(item, packets):
            self.queue.append(ins)
            out.append({"type": "insight", "insight": ins, "text": {"en": narrate(ins, "en"), "tr": narrate(ins, "tr")},
                        "evidence_points": self.evidence_points(ins), "zone": evidence_zone(ins, self.detectors.p)})
        if packets:
            out += self._direct(item.t, packets[-1])
            if len(self._batch) >= BATCH_FRAMES:
                out.insert(0, {"type": "state", "packets": self._batch})
                self._batch = []
        return out

    def _remember(self, ev: dict) -> None:
        if ev.get("start"):
            end = ev.get("end") or ev["start"]
            self._points[ev["seq"]] = (ev["t"], ev["type"], ev["team"], ev["start"]["x"], ev["start"]["y"], end["x"], end["y"])
        if ev["type"] == "shot":
            self._last_shot[ev["team"]] = ev

    def _cue(self, ev: dict) -> dict:
        cue = {"type": "event_cue", "t": ev["t"], "kind": ev["type"], "team": ev["team"], "seq": ev["seq"], "period": ev["period"],
               "player_id": ev.get("player_id"), "pan": self._last_pan}
        # A goal event sits on the goal line; the shot that scored says where it came from and how hard it was hit.
        src = self._last_shot.get(ev["team"], ev) if ev["type"] == "goal" else ev
        if ev["type"] in ("shot", "goal") and src.get("start"):
            cue["x"], cue["y"] = src["start"]["x"], src["start"]["y"]
        if src.get("speed_mps") is not None:
            cue["speed_mps"] = src["speed_mps"]
        if ev.get("outcome"):
            cue["outcome"] = ev["outcome"]
        if ev["type"] == "restart":
            cue["restart"] = ev["restart"]
        if ev["type"] == "pass" and ev.get("start") and ev.get("end"):
            cue["length_m"] = round(math.dist((ev["start"]["x"], ev["start"]["y"]), (ev["end"]["x"], ev["end"]["y"])), 1)
        return cue

    def evidence_points(self, ins: dict) -> list[dict]:
        """Where the evidence happened: one point per evidence seq (the last MAX_POINTS), in the global frame the client draws.
        A flank overload counts where passes ended, so its points are the pass ends; everything else uses the event's start."""
        out = []
        for seq in ins["evidence"][-MAX_POINTS:]:
            if seq not in self._points:
                continue
            t, type_, team, x, y, ex, ey = self._points[seq]
            if ins["type"] == "flank_overload":
                x, y = ex, ey
            out.append({"seq": seq, "t": t, "type": type_, "team": team, "x": x, "y": y})
        return out

    def _direct(self, now: float, state: dict) -> list[dict]:
        if not self.queue:
            return []
        out, keep = [], []
        for d in decide(self.queue, state, now, self.mode, self.spoken, self.favourite):
            if d.action == "hold":
                keep.append(d.insight)
            elif d.action == "speak":
                ins = d.insight
                self.spoken.append((now, ins["type"], ins["team"]))
                out.append({"type": "speech", "t": now, "insight_id": ins["insight_id"], "priority": ins["priority"], "team": ins["team"],
                            "persona": persona_for(self.mode), "evidence": ins["evidence"],
                            "text": {"en": narrate(ins, "en"), "tr": narrate(ins, "tr")}})
        self.queue = keep
        return out


def apply_listener_message(pipe: LivePipeline, msg: dict) -> None:
    """`set_mode` and `set_favourite` from a listener; anything else is ignored."""
    if msg.get("type") == "set_mode" and msg.get("mode") in SILENCE_S:
        pipe.mode = msg["mode"]
    elif msg.get("type") == "set_favourite" and msg.get("team") in ("HOME", "AWAY", None):
        pipe.favourite = msg["team"]


def warm_up(pipe: LivePipeline, match_dir: Path, start_minute: float) -> None:
    """Feed everything before `start_minute` through the pipeline unpaced and unpublished, so windows and baselines are filled."""
    t0 = start_minute * 60.0
    for item in iter_items(match_dir):
        if item.t >= t0:
            break
        pipe.feed(item)


def make_resolver(meta: dict) -> SpeechResolver:
    """HTG_ENV=azure: Foundry text + Azure voice (cache first). Anything else, or no credentials: templates, browser voice."""
    names = known_names(meta)
    if os.environ.get("HTG_ENV") == "azure":
        try:
            from htg.speech.azure import AzureSpeech

            return SpeechResolver(get_narrator(), AzureSpeech(), names, True)
        except Exception as e:
            print(f"Azure adapters unavailable ({type(e).__name__}); using templates and browser voice.")
    return SpeechResolver(TemplateNarrator(), NoSpeech(), names, False)


async def main(seed: int, speed: float, start_minute: float, mode: str, port: int) -> None:
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    load_env()
    meta = json.loads((Path(match_dir) / "meta.json").read_text())
    pipe, resolver = LivePipeline(meta, mode, speed), make_resolver(meta)

    def on_message(msg: dict) -> None:  # the only things a listener may send: the listening mode and the favourite club
        apply_listener_message(pipe, msg)

    bus = WebSocketBroadcaster(port=port, on_message=on_message)
    await bus.start()
    print(f"seed {seed}, speed {speed}x, from minute {start_minute}, mode {mode}. Open web/live.html (ws://localhost:{bus.port}).")
    print("Waiting for a listener...")
    await bus.wait_for_client()
    await asyncio.to_thread(warm_up, pipe, match_dir, start_minute)
    await bus.publish(pipe.hello())
    insights: dict[str, dict] = {}
    tasks: set[asyncio.Task] = set()
    now = start_minute * 60.0

    async def deliver(msg: dict) -> None:
        final = await resolver.resolve(msg, insights[msg["insight_id"]])
        if not is_stale(final, now):
            await bus.publish(final)

    async for item in FileEventSource(match_dir, speed, start_minute):
        now = item.t
        for msg in pipe.feed(item):
            if msg["type"] == "speech":
                task = asyncio.create_task(deliver(msg))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
                continue
            if msg["type"] == "insight":
                insights[msg["insight"]["insight_id"]] = msg["insight"]
            await bus.publish(msg)
    await asyncio.gather(*tasks)
    await bus.close()
    print("Match finished.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--start-minute", type=float, default=0.0)
    ap.add_argument("--mode", choices=sorted(SILENCE_S), default="casual")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    try:
        asyncio.run(main(a.seed, a.speed, a.start_minute, a.mode, a.port))
    except KeyboardInterrupt:
        pass
