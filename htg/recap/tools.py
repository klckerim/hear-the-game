"""Recap tools: deterministic facts about a match **up to time `t`**, for the Recap agent and the template recap.

Pure functions over a `MatchRecord`. Nothing after `t` is ever returned, and `truth.json` is never read. Insights are detected once
over the whole replay; the detectors are causal (no look-ahead), so keeping those with `insight.t <= t` equals running them up to `t`.
Every number is rounded the way it may be spoken: percentages and counts as integers, minutes as whole match minutes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from htg.engine.detectors import Detectors
from htg.engine.state import StateEngine
from htg.replay import iter_items

SIDES = ("HOME", "AWAY")
OTHER = {"HOME": "AWAY", "AWAY": "HOME"}
ON_BALL = {"pass", "carry", "shot"}
ON_TARGET = {"saved", "goal"}


@dataclass(frozen=True)
class MatchRecord:
    meta: dict
    events: list[dict]
    physical: list[dict]
    ball_t: np.ndarray  # in-play ball frames only
    ball_home: np.ndarray  # True where HOME has the ball
    insights: list[dict]

    @classmethod
    def load(cls, match_dir: Path) -> MatchRecord:
        match_dir = Path(match_dir)
        meta = json.loads((match_dir / "meta.json").read_text())
        events = [json.loads(line) for line in (match_dir / "events.jsonl").read_text().splitlines() if line]
        physical = [json.loads(line) for line in (match_dir / "physical.jsonl").read_text().splitlines() if line]
        ball = pd.read_parquet(match_dir / "ball.parquet", columns=["t", "team", "in_play"])
        ball = ball[ball["in_play"].astype(bool)]
        return cls(meta, events, physical, ball["t"].to_numpy(), (ball["team"] == "HOME").to_numpy(), _detect(meta, match_dir))

    def team_name(self, side: str) -> dict[str, str]:
        return self.meta["teams"][side]["name"]

    def players(self) -> dict[str, dict]:
        return {p["player_id"]: {**p, "team": side} for side, t in self.meta["teams"].items() for p in t["players"]}


def _detect(meta: dict, match_dir: Path) -> list[dict]:
    engine, det, out = StateEngine.from_calibration(), Detectors(meta), []
    for item in iter_items(match_dir):
        out += det.step(item, engine.step(item))
    return out


def _minute(t: float) -> int:
    return int(t // 60)


def _window(rec: MatchRecord, t: float, from_min: float | None, to_min: float | None) -> tuple[float, float]:
    """Seconds [lo, hi] of the asked window, clamped to [0, t]: a window can never reach past `t`.

    A `to_min` at the current minute or later means "now": the agent says "to minute 70" at 70:38 and must not lose the last 38 s."""
    lo = max(0.0, 60.0 * (from_min or 0))
    hi = t if to_min is None or to_min >= _minute(t) else min(t, 60.0 * to_min)
    return min(lo, hi), hi


def _team(rec: MatchRecord, side: str) -> dict[str, str]:
    n = rec.team_name(side)
    return {"side": side, "team_en": n["en"], "team_tr": n["tr"]}


def _pct(n: float, d: float) -> int | None:
    return round(100 * n / d) if d else None


def get_score(rec: MatchRecord, t: float) -> dict[str, Any]:
    """Score, minutes played, period and the goals so far (minute, team, scorer)."""
    names = {pid: p["name"] for pid, p in rec.players().items()}
    past = [e for e in rec.events if e["t"] <= t]
    goals = [e for e in past if e["type"] == "goal"]
    score = {s: sum(g["team"] == s for g in goals) for s in SIDES}
    return {"home": _team(rec, "HOME"), "away": _team(rec, "AWAY"), "home_score": score["HOME"], "away_score": score["AWAY"],
            "minutes_played": _minute(t), "period": past[-1]["period"] if past else 1,
            "full_time": any(e["type"] == "period_end" and e["period"] == 2 for e in past),
            "goals": [{"minute": _minute(g["t"]), "team_en": rec.team_name(g["team"])["en"], "team_tr": rec.team_name(g["team"])["tr"],
                       "player": names.get(g.get("player_id") or "", "")} for g in goals]}


def get_stats(rec: MatchRecord, t: float, from_min: float | None = None, to_min: float | None = None) -> dict[str, Any]:
    """Per team, between from_min and to_min (never after t): possession, shots, passes, pressing, corners, fouls."""
    lo, hi = _window(rec, t, from_min, to_min)
    evs = [e for e in rec.events if lo < e["t"] <= hi]
    mask = (rec.ball_t > lo) & (rec.ball_t <= hi)
    frames, home_frames = int(mask.sum()), int(rec.ball_home[mask].sum())
    teams = {}
    for side in SIDES:
        mine = [e for e in evs if e["team"] == side]
        shots = [e for e in mine if e["type"] == "shot"]
        passes = [e for e in mine if e["type"] == "pass"]
        opp_actions = [e for e in evs if e["team"] == OTHER[side] and e["type"] in ON_BALL]
        own = home_frames if side == "HOME" else frames - home_frames
        teams[side.lower()] = {
            **_team(rec, side), "possession_pct": _pct(own, frames), "shots": len(shots),
            "shots_on_target": sum(e.get("outcome") in ON_TARGET for e in shots),
            "pass_completion_pct": _pct(sum(e.get("outcome") == "complete" for e in passes), len(passes)),
            "pressing_pct": _pct(sum(bool(e.get("under_pressure")) for e in opp_actions), len(opp_actions)),
            "corners": sum(e["type"] == "restart" and e.get("restart") == "corner" for e in mine),
            "fouls": sum(e["type"] == "foul" for e in mine)}
    return {"from_minute": _minute(lo), "to_minute": _minute(hi), "length_min": round((hi - lo) / 60), **teams,
            "note": "pressing_pct = share of the opponent's on-ball actions made under this team's pressure"}


def get_insights(rec: MatchRecord, t: float, from_min: float | None = None, to_min: float | None = None) -> dict[str, Any]:
    """The Insights detected between from_min and to_min (never after t). Danger-only chances are left out: they are not spoken."""
    lo, hi = _window(rec, t, from_min, to_min)
    names = {pid: p["name"] for pid, p in rec.players().items()}
    out = []
    for i in rec.insights:
        if not lo < i["t"] <= hi or i["claim_facts"].get("source") == "danger":
            continue
        out.append({"minute": _minute(i["t"]), "type": i["type"], "team": i["team"],
                    "player": names.get(i.get("player_id") or "", None), "claim_facts": i["claim_facts"]})
    return {"from_minute": _minute(lo), "to_minute": _minute(hi), "insights": out}


def find_player(rec: MatchRecord, player: str) -> str | None:
    """A player id from an id ("A10") or a name (case-insensitive)."""
    players = rec.players()
    if player in players:
        return player
    return next((pid for pid, p in players.items() if p["name"].casefold() == str(player).casefold()), None)


def get_player(rec: MatchRecord, t: float, player: str, from_min: float | None = None, to_min: float | None = None) -> dict[str, Any]:
    """One player between from_min and to_min (never after t): touches, passes, shots, high-speed running vs his earlier level."""
    pid = find_player(rec, player)
    if pid is None:
        return {"error": f"unknown player {player!r}"}
    p = rec.players()[pid]
    lo, hi = _window(rec, t, from_min, to_min)
    mine = [e for e in rec.events if lo < e["t"] <= hi and e.get("player_id") == pid]
    passes = [e for e in mine if e["type"] == "pass"]
    # A physical row for minute m is known at the end of that minute, (m + 1) * 60.
    rows = [r for r in rec.physical if r["player_id"] == pid and (r["minute"] + 1) * 60 <= t]
    now = [r["hsr_m"] for r in rows if lo <= r["minute"] * 60 < hi]
    before = [r["hsr_m"] for r in rows if r["minute"] * 60 < lo]
    now_avg = sum(now) / len(now) if now else None
    before_avg = sum(before) / len(before) if before else None
    return {"player": p["name"], **_team(rec, p["team"]), "from_minute": _minute(lo), "to_minute": _minute(hi),
            "touches": sum(e["type"] in ON_BALL for e in mine), "passes": len(passes),
            "pass_completion_pct": _pct(sum(e.get("outcome") == "complete" for e in passes), len(passes)),
            "shots": sum(e["type"] == "shot" for e in mine),
            "hsr_m_per_min": round(now_avg) if now_avg is not None else None,
            "hsr_vs_earlier_pct": _pct(now_avg, before_avg) if now_avg is not None and before_avg else None}
