"""Live commentary for one listener session: segments in, `commentary` messages out, one segment at a time.

Facts + the last 3 lines -> Foundry -> Verifier -> commentary voice -> send, then the next segment. A backlog skips to the newest
finished segment (the skipped ones are counted; callouts fill the gap). The client plays a line at its match time `t` (segment end +
offset), `delay_s` behind the server, so a line ready later than `t + delay_s - LATE_MARGIN_S` in server match time is dropped.
When the live line is late or fails, the verified line an earlier session cached for that segment plays instead ("fallback").
Listeners of the same stretch at the same time share one model call per segment (`_shared`); the clip cache shares the voice.
"""
from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from htg import telemetry
from htg.adapters.base import Speech
from htg.commentary.commentator import SPEECH_STYLE, Model, cache_path, commentate, load_cached, save_cached
from htg.commentary.segments import Segment
from services.engine.resolve import MP3_BYTES_PER_S

LATE_MARGIN_S = 3.0
SHARE_S = 60.0  # a model call another session started this recently (wall clock) is shared, not repeated
_shared: dict[str, tuple[float, asyncio.Future]] = {}


@dataclass
class Counts:
    segments: int = 0
    lines: int = 0
    live: int = 0
    fallback: int = 0
    verifier_dropped: int = 0
    late: int = 0
    skipped: int = 0
    errors: int = 0
    silent: int = 0
    latency_s: list[float] = field(default_factory=list)


def shared_call(key: str, make: Callable[[], Awaitable[dict]]) -> asyncio.Future:
    """The model call for `key`: the one a session started within SHARE_S, else a new one. Old entries are forgotten."""
    now = time.monotonic()
    for k in [k for k, (t, _) in _shared.items() if now - t > SHARE_S]:
        del _shared[k]
    if key not in _shared:
        fut = asyncio.ensure_future(make())
        fut.add_done_callback(lambda f: f.cancelled() or f.exception())  # an error nobody waited for is not logged as unretrieved
        _shared[key] = (now, fut)
    return _shared[key][1]


class CommentaryStream:
    def __init__(self, model: Model, speech: Speech, names: list[str], seed: object, delay_s: float,
                 speed: float, lang: str, send: Callable[[dict], Awaitable[None]], clock: Callable[[], float]):
        self.model, self.speech, self.names, self.seed = model, speech, names, seed
        self.delay_s, self.speed, self.lang, self.send, self.clock = delay_s, speed, lang, send, clock  # clock: server match time
        self.recent: list[str] = []
        self.counts = Counts()
        self._pending: list[tuple[Segment, float]] = []
        self._wake = asyncio.Event()
        self._closed = False

    def push(self, seg: Segment) -> None:
        """A finished segment from the replay loop; never blocks."""
        self._pending.append((seg, time.perf_counter()))
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    async def run(self) -> None:
        while True:
            if not self._pending:
                if self._closed:
                    return
                await self._wake.wait()
                self._wake.clear()
                continue
            (seg, t_closed), skipped = self._pending[-1], len(self._pending) - 1
            self._pending.clear()
            if skipped:
                self.counts.skipped += skipped
                telemetry.commentary_dropped.add(skipped, {"reason": "skipped"})
            try:
                await self._one(seg, t_closed)
            except Exception:  # never let one segment end the commentary
                self.counts.errors += 1

    def _deadline(self, t: float) -> float:
        return t + self.delay_s - LATE_MARGIN_S

    async def _one(self, seg: Segment, t_closed: float) -> None:
        self.counts.segments += 1
        path = cache_path(self.seed, seg.segment_id, self.model.name)
        budget = (self._deadline(seg.t1) - self.clock()) / self.speed
        with telemetry.tracer.start_as_current_span("htg.commentary.segment") as span:
            span.set_attribute("segment.id", seg.segment_id)
            span.set_attribute("facts.size", len(seg.facts))
            span.set_attribute("budget_s", round(budget, 2))
            source, lines, audio = "live", None, None
            if budget > 0:
                try:
                    lines, audio = await asyncio.wait_for(self._live(seg, path), budget)
                except Exception:  # timeout, model or voice error
                    lines = None
            if lines is None:
                source, lines = "fallback", await asyncio.to_thread(load_cached, path)
                audio = await asyncio.to_thread(self._voice, lines) if lines else None
            latency = round(time.perf_counter() - t_closed, 2)
            span.set_attribute("source", source)
            span.set_attribute("latency_s", latency)
            span.set_attribute("cache_hit", source == "fallback" and bool(lines))
            span.set_attribute("lines", len(lines or []))
            if source == "live":
                self.counts.latency_s.append(latency)
                telemetry.commentary_ms.record(latency * 1000)
            if not lines:
                self.counts.silent += 1
                return
            for line, clip in zip(lines, audio or [None] * len(lines), strict=True):
                if line.get(self.lang) is None:
                    continue
                t = round(seg.t1 + line["offset_s"], 2)
                if self.clock() > self._deadline(t):
                    self.counts.late += 1
                    telemetry.commentary_dropped.add(1, {"reason": "late"})
                    continue
                self.counts.lines += 1
                setattr(self.counts, source, getattr(self.counts, source) + 1)
                telemetry.commentary_lines.add(1, {"source": source, "lang": self.lang})
                self.recent.append(line["en"] or line["tr"])
                await self.send({"type": "commentary", "t": t, "segment": seg.segment_id, "goal": seg.goal, "style": line["style"],
                                 "text": {k: line[k] for k in ("en", "tr") if line[k]}, "source": source, "latency_s": latency,
                                 "audio": {self.lang: base64.b64encode(clip).decode() if clip else None},
                                 "duration_s": {self.lang: round(len(clip) / MP3_BYTES_PER_S, 1) if clip else None}})
            self.recent = self.recent[-3:]

    async def _live(self, seg: Segment, path) -> tuple[list[dict], list[bytes | None]]:  # noqa: ANN001
        recent = list(self.recent)

        async def call() -> dict:
            out = await asyncio.to_thread(commentate, seg, self.model, self.names, recent)
            await asyncio.to_thread(save_cached, path, out["lines"])  # the fallback for later sessions
            return out

        out = await asyncio.shield(shared_call(str(path), call))  # a timeout here leaves the shared call running
        if out["dropped"]:
            self.counts.verifier_dropped += out["dropped"]
            telemetry.commentary_dropped.add(out["dropped"], {"reason": "verifier"})
        return out["lines"], await asyncio.to_thread(self._voice, out["lines"])

    def _voice(self, lines: list[dict]) -> list[bytes | None]:
        """The listener's language only; the other text rides along for the dual caption."""
        speak = getattr(self.speech, "commentate", None)
        out = []
        for line in lines:
            text = line.get(self.lang)
            out.append(speak(text, self.lang, SPEECH_STYLE[self.lang][line["style"]]) if speak and text else None)
        return out
