"""State engine: match items in, 10 Hz state packets out.

`StateEngine.step(item)` is pure bookkeeping: no I/O, no clock, no randomness. Time only comes from the items,
so the same stream always gives the same packets. One packet is emitted per ball frame; events update the
internal state that the next packet reads. Packets follow `schemas/state.schema.json`.
"""
from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

import numpy as np

from htg.pitch import GRID_X, GRID_Y, LENGTH, WIDTH, flank_pan, to_attacking
from htg.replay import Item

CAL_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration" / "calibration.json"

# 99th percentile of the raw xT at the ball over in-play frames, mean of seeds 1-10 (tuning seeds), so that
# danger = xT / DANGER_P99 reaches about 1 in the most dangerous 1% of a match. Recompute with `p99_xt`.
DANGER_P99 = 0.125

PRESSURE_HALF_LIFE_S = 4.0
PRESSURE_SCALE = 1.5  # pressure = 1 - exp(-decayed_count / PRESSURE_SCALE): one fresh event 0.49, two 0.74
TEMPO_WINDOW_S = 60.0
TEMPO_MIN_WINDOW_S = 10.0  # avoid wild rates in the first seconds of a replay
CONTROL_WINDOW_S = 300.0
ON_BALL = {"pass", "carry", "shot"}


def xt_at(xt: np.ndarray, xa: float, ya: float) -> float:
    """Bilinear xT at an attacking-frame position. `xt` is the (GRID_X, GRID_Y) grid, values at cell centres."""
    fx = min(max(xa / LENGTH * GRID_X - 0.5, 0.0), GRID_X - 1.0)
    fy = min(max(ya / WIDTH * GRID_Y - 0.5, 0.0), GRID_Y - 1.0)
    i0, j0 = int(fx), int(fy)
    i1, j1 = min(i0 + 1, GRID_X - 1), min(j0 + 1, GRID_Y - 1)
    tx, ty = fx - i0, fy - j0
    top = xt[i0, j0] * (1 - ty) + xt[i0, j1] * ty
    bottom = xt[i1, j0] * (1 - ty) + xt[i1, j1] * ty
    return float(top * (1 - tx) + bottom * tx)


class StateEngine:
    def __init__(self, xt: np.ndarray, actions_per_min: float, danger_p99: float = DANGER_P99):
        self.xt = xt
        self.actions_per_min = actions_per_min
        self.danger_p99 = danger_p99
        self._press: dict[str, tuple[float, float]] = {"HOME": (0.0, 0.0), "AWAY": (0.0, 0.0)}  # team -> (count, t)
        self._actions: deque[float] = deque()
        self._poss: deque[tuple[float, str]] = deque()
        self._home_frames = 0
        self._t0: float | None = None

    @classmethod
    def from_calibration(cls, path: Path = CAL_PATH, danger_p99: float = DANGER_P99) -> StateEngine:
        sb = json.loads(Path(path).read_text())["statsbomb"]
        per_match = sb["per_match"]
        # Passes, carries and shots per minute of a 90-minute match: the on-ball rate a tempo of 0.5 stands for.
        actions_per_min = (per_match["passes"] + per_match["carries"] + per_match["shots"]) / 90.0
        return cls(np.array(sb["xt"]).reshape(GRID_X, GRID_Y), actions_per_min, danger_p99)

    def step(self, item: Item) -> list[dict]:
        if self._t0 is None:
            self._t0 = item.t
        if item.kind == "event":
            self._on_event(item.data)
            return []
        if item.kind == "ball":
            return [self._packet(item.data)]
        return []  # physical rows belong to the detectors

    def _on_event(self, ev: dict) -> None:
        if ev["type"] == "pressure":
            count, t = self._press[ev["team"]]
            self._press[ev["team"]] = (self._decayed(count, t, ev["t"]) + 1.0, ev["t"])
        elif ev["type"] in ON_BALL:
            self._actions.append(ev["t"])

    @staticmethod
    def _decayed(count: float, since: float, now: float) -> float:
        return count * 0.5 ** (max(now - since, 0.0) / PRESSURE_HALF_LIFE_S)

    def _packet(self, b: dict) -> dict:
        t, team, in_play = b["t"], b["team"], bool(b["in_play"])
        xa, ya = to_attacking(b["x"], b["y"], team)

        danger = min(xt_at(self.xt, xa, ya) / self.danger_p99, 1.0) if in_play else 0.0

        presser = "AWAY" if team == "HOME" else "HOME"
        count, since = self._press[presser]
        pressure = 1.0 - math.exp(-self._decayed(count, since, t) / PRESSURE_SCALE)

        while self._actions and self._actions[0] < t - TEMPO_WINDOW_S:
            self._actions.popleft()
        window = min(max(t - self._t0, TEMPO_MIN_WINDOW_S), TEMPO_WINDOW_S)
        tempo = min(len(self._actions) / window * 60.0 / (2.0 * self.actions_per_min), 1.0)

        if in_play:
            self._poss.append((t, team))
            self._home_frames += team == "HOME"
        while self._poss and self._poss[0][0] < t - CONTROL_WINDOW_S:
            self._home_frames -= self._poss.popleft()[1] == "HOME"
        control = self._home_frames / len(self._poss) if self._poss else 0.5

        return {
            "t": round(t, 3), "x": round(b["x"], 2), "y": round(b["y"], 2), "team": team, "in_play": in_play,
            "danger": round(danger, 4), "pressure": round(pressure, 4), "pan": round(flank_pan(xa, ya), 3),
            "tempo": round(tempo, 4), "control": round(control, 4),
        }


def p99_xt(xt: np.ndarray, items) -> float:
    """99th percentile of raw xT at the ball over the in-play frames of one match (used to set DANGER_P99)."""
    vals = [xt_at(xt, *to_attacking(i.data["x"], i.data["y"], i.data["team"])) for i in items if i.kind == "ball" and i.data["in_play"]]
    return float(np.percentile(vals, 99))
