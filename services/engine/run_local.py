"""Local live slice: replay -> state engine -> detectors -> Director -> WebSocket.

    python -m services.engine.run_local --seed 1 --speed 1 --start-minute 10

then open `web/live.html` (it connects to ws://localhost:8765). Replay starts when the first listener connects.
Messages (JSON, one per WebSocket frame):
    hello      match info, replay speed, mode (first message)
    state      batch of 10 Hz state packets, every ~200 ms of match time
    event_cue  one sound cue (pass, shot, save, goal, whistle ...)
    insight    a detected Insight (for the log)
    speech     the Insight the Director decided to tell now, template text in EN and TR
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from htg.adapters.local import FileEventSource, WebSocketBroadcaster
from htg.engine.detectors import Detectors
from htg.engine.director import SILENCE_S, decide
from htg.engine.state import StateEngine
from htg.generate import OUT_DIR, generate
from htg.narration.templates import narrate
from htg.replay import Item

BATCH_FRAMES = 2  # 10 Hz frames per `state` message = 200 ms
CUES = {"pass", "shot", "save", "goal", "out", "foul", "kickoff", "restart"}


class LivePipeline:
    """Feeds items in, returns the messages to broadcast. Pure bookkeeping, so `speed=inf` runs are reproducible."""

    def __init__(self, meta: dict, mode: str = "casual", speed: float = 1.0):
        self.meta, self.mode, self.speed = meta, mode, speed
        self.engine, self.detectors = StateEngine.from_calibration(), Detectors(meta)
        self.queue: list[dict] = []
        self.spoken: list[tuple[float, str, str | None]] = []
        self._batch: list[dict] = []
        self._last_pan = 0.0

    def hello(self) -> dict:
        teams = {k: {"name_en": v["name"]["en"], "name_tr": v["name"]["tr"], "color": v["color"]} for k, v in self.meta["teams"].items()}
        return {"type": "hello", "match_id": self.meta["match_id"], "teams": teams, "mode": self.mode,
                "speed": self.speed if self.speed != float("inf") else 1.0}

    def feed(self, item: Item) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        packets = self.engine.step(item)
        if packets:
            self._last_pan = packets[-1]["pan"]
            self._batch += packets
        if item.kind == "event" and item.data["type"] in CUES:
            ev = item.data
            out.append({"type": "event_cue", "t": ev["t"], "kind": ev["type"], "team": ev["team"], "seq": ev["seq"], "pan": self._last_pan})
        for ins in self.detectors.step(item, packets):
            self.queue.append(ins)
            out.append({"type": "insight", "insight": ins})
        if packets:
            out += self._direct(item.t, packets[-1])
            if len(self._batch) >= BATCH_FRAMES:
                out.insert(0, {"type": "state", "packets": self._batch})
                self._batch = []
        return out

    def _direct(self, now: float, state: dict) -> list[dict]:
        if not self.queue:
            return []
        out, keep = [], []
        for d in decide(self.queue, state, now, self.mode, self.spoken):
            if d.action == "hold":
                keep.append(d.insight)
            elif d.action == "speak":
                ins = d.insight
                self.spoken.append((now, ins["type"], ins["team"]))
                out.append({"type": "speech", "t": now, "insight_id": ins["insight_id"], "priority": ins["priority"],
                            "evidence": ins["evidence"], "text": {"en": narrate(ins, "en"), "tr": narrate(ins, "tr")}})
        self.queue = keep
        return out


async def main(seed: int, speed: float, start_minute: float, mode: str, port: int) -> None:
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    meta = json.loads((Path(match_dir) / "meta.json").read_text())
    pipe, bus = LivePipeline(meta, mode, speed), WebSocketBroadcaster(port=port)
    await bus.start()
    print(f"seed {seed}, speed {speed}x, from minute {start_minute}, mode {mode}. Open web/live.html (ws://localhost:{bus.port}).")
    print("Waiting for a listener...")
    await bus.wait_for_client()
    await bus.publish(pipe.hello())
    async for item in FileEventSource(match_dir, speed, start_minute):
        for msg in pipe.feed(item):
            await bus.publish(msg)
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
