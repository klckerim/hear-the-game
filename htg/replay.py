"""Replay a synthetic match as one time-ordered stream.

Merges `events.jsonl`, `ball.parquet` (10 Hz) and `physical.jsonl` (one row per player-minute) into `Item`s.
Order is deterministic: by time, and for equal times ball frame, then events by `seq`, then physical rows.
A physical row summarises a finished minute, so it is released at the end of that minute (no look-ahead).

`truth.json` is never read here.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

Kind = Literal["ball", "event", "physical"]
_RANK = {"ball": 0, "event": 1, "physical": 2}


@dataclass(frozen=True)
class Item:
    t: float
    kind: Kind
    data: dict[str, Any]


def iter_items(match_dir: Path, start_minute: float = 0) -> Iterator[Item]:
    """All items of a match in replay order, starting at `start_minute` of match time."""
    match_dir = Path(match_dir)
    keyed: list[tuple[float, int, int, Item]] = []

    for row in pd.read_parquet(match_dir / "ball.parquet").to_dict("records"):
        keyed.append((row["t"], _RANK["ball"], 0, Item(row["t"], "ball", row)))
    with (match_dir / "events.jsonl").open() as f:
        for line in f:
            ev = json.loads(line)
            keyed.append((ev["t"], _RANK["event"], ev["seq"], Item(ev["t"], "event", ev)))
    with (match_dir / "physical.jsonl").open() as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            t = (row["minute"] + 1) * 60.0
            keyed.append((t, _RANK["physical"], i, Item(t, "physical", row)))

    keyed.sort(key=lambda k: k[:3])
    t0 = start_minute * 60.0
    for t, _, _, item in keyed:
        if t >= t0:
            yield item


async def replay(match_dir: Path, speed: float = 1.0, start_minute: float = 0, lead_s: float = 0.0) -> AsyncIterator[Item]:
    """Yield items paced at `speed` x real time; `speed=inf` yields as fast as possible (offline / eval). The first `lead_s` of match
    time come at once (a listener's broadcast-delay buffer), then pacing continues `lead_s` ahead.

    Pacing only delays delivery; the sequence of items does not depend on it.
    """
    realtime = math.isfinite(speed)
    if realtime and speed <= 0:
        raise ValueError("speed must be positive")
    t0 = start_minute * 60.0
    started = time.monotonic()
    for item in iter_items(match_dir, start_minute):
        if realtime:
            delay = started + (item.t - t0 - lead_s) / speed - time.monotonic()
            await asyncio.sleep(max(delay, 0.0))
        else:
            await asyncio.sleep(0)
        yield item
