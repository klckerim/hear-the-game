"""Detectors: match items in, evidence-backed Insights out (`schemas/insight.schema.json`).

`Detectors.step(item, packets)` is pure bookkeeping like the state engine: no I/O, no clock, no randomness. Time only
comes from the items. Every number a sentence may use is in `claim_facts`; `evidence` lists the event `seq`s behind it.
Thresholds live in `Params`; defaults were tuned on seeds 1-10 only (two rounds). `truth.json` is never read here.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from htg.pitch import to_attacking
from htg.replay import Item

OTHER = {"HOME": "AWAY", "AWAY": "HOME"}
ON_BALL = {"pass", "carry", "shot"}
MAX_EVIDENCE = 10
SIDE_TR = {"left": "sol", "right": "sağ"}


@dataclass(frozen=True)
class Params:
    eval_every_s: float = 30.0
    # pressure_shift: share of the opponent's actions under pressure, last window vs before it
    press_window_s: float = 300.0
    press_ratio: float = 1.7
    press_min_actions: int = 25
    # tempo_change: median gap between a team's on-ball actions, last window vs before it
    tempo_window_s: float = 420.0
    tempo_ratio: float = 1.5
    tempo_min_gaps: int = 30
    tempo_max_gap_s: float = 10.0  # longer gaps are turnovers / stoppages, not tempo
    # flank_overload: share of a team's passes ending in one flank (attacking frame), last window vs before it
    flank_window_s: float = 480.0
    flank_ratio: float = 2.0
    flank_min_passes: int = 25
    flank_high_y: float = 42.5  # left flank
    flank_low_y: float = 25.5  # right flank
    # physical_drop: a player's high-speed running, last minutes vs his own earlier minutes
    phys_recent_min: int = 8
    phys_ratio: float = 0.5
    phys_min_earlier: int = 10
    phys_min_hsr: float = 2.0  # m/min earlier average; skips goalkeepers
    # chance: shots, or the ball in a very dangerous place
    danger_threshold: float = 0.9
    danger_cooldown_s: float = 120.0
    shot_quiet_s: float = 20.0  # no danger chance this soon after a shot chance
    cooldown_s: dict[str, float] | None = None  # per insight type; defaults below

    def cooldown(self, type_: str) -> float:
        return (self.cooldown_s or {}).get(type_, DEFAULT_COOLDOWN_S.get(type_, 300.0))


DEFAULT_COOLDOWN_S = {"pressure_shift": 300.0, "tempo_change": 300.0, "flank_overload": 480.0, "physical_drop": 900.0}
TTL_S = {"pressure_shift": 120.0, "tempo_change": 120.0, "flank_overload": 120.0, "physical_drop": 180.0, "goal": 60.0, "chance": 20.0}
PRIORITY = {"pressure_shift": 3, "tempo_change": 2, "flank_overload": 2, "physical_drop": 3, "goal": 5, "chance": 4}


class Detectors:
    def __init__(self, meta: dict, params: Params | None = None):
        self.p = params or Params()
        self.match_id = meta.get("match_id", "unknown")
        self.teams = meta["teams"]
        self.names = {pl["player_id"]: pl["name"] for t in self.teams.values() for pl in t["players"]}
        self._actions: dict[str, list[dict]] = {"HOME": [], "AWAY": []}  # on-ball events per team
        self._by_player: dict[str, list[tuple[float, int]]] = {}
        self._phys: dict[str, list[tuple[int, float]]] = {}
        self._last_fired: dict[tuple, float] = {}
        self._next_eval = 0.0
        self._last_seq = 0
        self._score = {"HOME": 0, "AWAY": 0}
        self._last_shot: dict[str, dict] = {}
        self._last_shot_chance = -1e9
        self._last_danger_chance = -1e9

    @property
    def score(self) -> dict[str, int]:
        return dict(self._score)

    def step(self, item: Item, packets: list[dict] | tuple = ()) -> list[dict]:
        out: list[dict] = []
        if item.kind == "event":
            out += self._on_event(item.data)
        elif item.kind == "physical":
            out += self._on_physical(item.t, item.data)
        for packet in packets:
            out += self._on_packet(packet)
        return out

    # ------------------------------------------------------------------ events
    def _on_event(self, ev: dict) -> list[dict]:
        t, out = ev["t"], []
        self._last_seq = ev["seq"]
        if ev["type"] in ON_BALL:
            self._actions[ev["team"]].append(ev)
            self._by_player.setdefault(ev.get("player_id") or "", []).append((t, ev["seq"]))
        if ev["type"] == "shot":
            self._last_shot[ev["team"]] = ev
            if ev.get("outcome") != "goal":
                out.append(self._shot_chance(ev))
        elif ev["type"] == "goal":
            out.append(self._goal(ev))
        if t >= self._next_eval:
            self._next_eval = t + self.p.eval_every_s
            for team in ("HOME", "AWAY"):
                out += self._periodic(t, team)
        return [i for i in out if i]

    def _periodic(self, t: float, team: str) -> list[dict | None]:
        return [self._pressure_shift(t, team), self._tempo_change(t, team), self._flank_overload(t, team)]

    def _ready(self, key: tuple, t: float, type_: str) -> bool:
        return t - self._last_fired.get(key, -1e9) >= self.p.cooldown(type_)

    def _make(self, t: float, type_: str, team: str | None, facts: dict[str, Any], evidence: list[int], confidence: float,
              player_id: str | None = None, key: tuple | None = None) -> dict:
        if key:
            self._last_fired[key] = t
        who = player_id or team or "match"
        return {
            "insight_id": f"{self.match_id}:{type_}:{who}:{int(t)}", "match_id": self.match_id, "t": round(t, 3), "type": type_,
            "team": team, "player_id": player_id, "claim_facts": facts, "evidence": evidence[-MAX_EVIDENCE:] or [self._last_seq],
            "confidence": round(min(max(confidence, 0.0), 1.0), 2), "priority": PRIORITY[type_], "expires_at": round(t + TTL_S[type_], 3),
        }

    def _team_facts(self, team: str, opponent: bool = True) -> dict[str, str]:
        me, other = self.teams[team]["name"], self.teams[OTHER[team]]["name"]
        out = {"team_en": me["en"], "team_tr": me["tr"]}
        return {**out, "opponent_en": other["en"], "opponent_tr": other["tr"]} if opponent else out

    # ------------------------------------------------------------------ periodic detectors
    def _pressure_shift(self, t: float, team: str) -> dict | None:
        """`team` presses: how many of the opponent's on-ball actions are under pressure, now vs before."""
        p, key = self.p, ("pressure_shift", team)
        if not self._ready(key, t, "pressure_shift"):
            return None
        acts = self._actions[OTHER[team]]
        recent = [a for a in acts if a["t"] > t - p.press_window_s]
        before = [a for a in acts if a["t"] <= t - p.press_window_s]
        if len(recent) < p.press_min_actions or len(before) < p.press_min_actions:
            return None
        now = sum(bool(a.get("under_pressure")) for a in recent) / len(recent)
        was = sum(bool(a.get("under_pressure")) for a in before) / len(before)
        ratio = now / max(was, 0.05)
        if ratio < p.press_ratio:
            return None
        facts = {**self._team_facts(team), "share_now_pct": round(100 * now), "share_before_pct": round(100 * was),
                 "recent_min": round(p.press_window_s / 60)}
        evidence = [a["seq"] for a in recent if a.get("under_pressure")]
        return self._make(t, "pressure_shift", team, facts, evidence, ratio / 2, key=key)

    def _tempo_change(self, t: float, team: str) -> dict | None:
        """Median gap between consecutive on-ball actions of one possession, now vs before. Fires when play slows."""
        p, key = self.p, ("tempo_change", team)
        if not self._ready(key, t, "tempo_change"):
            return None
        acts = self._actions[team]
        recent, before = [], []
        for a, b in zip(acts, acts[1:], strict=False):
            gap = b["t"] - a["t"]
            if a.get("possession_id") != b.get("possession_id") or gap > p.tempo_max_gap_s:
                continue
            (recent if b["t"] > t - p.tempo_window_s else before).append((gap, b["seq"]))
        if len(recent) < p.tempo_min_gaps or len(before) < p.tempo_min_gaps:
            return None
        now = statistics.median(g for g, _ in recent)
        was = statistics.median(g for g, _ in before)
        ratio = now / max(was, 0.1)
        if ratio < p.tempo_ratio:
            return None
        facts = {**self._team_facts(team), "gap_now_s": round(now, 1), "gap_before_s": round(was, 1),
                 "slower_pct": round(100 * (ratio - 1)), "recent_min": round(p.tempo_window_s / 60)}
        return self._make(t, "tempo_change", team, facts, [s for _, s in recent], ratio / 2, key=key)

    def _flank_side(self, ev: dict, team: str) -> str | None:
        _, ya = to_attacking(ev["end"]["x"], ev["end"]["y"], team)
        return "left" if ya > self.p.flank_high_y else "right" if ya < self.p.flank_low_y else None

    def _flank_overload(self, t: float, team: str) -> dict | None:
        p, key = self.p, ("flank_overload", team)
        if not self._ready(key, t, "flank_overload"):
            return None
        passes = [a for a in self._actions[team] if a["type"] == "pass" and a.get("end")]
        recent = [a for a in passes if a["t"] > t - p.flank_window_s]
        before = [a for a in passes if a["t"] <= t - p.flank_window_s]
        if len(recent) < p.flank_min_passes or len(before) < p.flank_min_passes:
            return None
        best: tuple[float, str, float, list[int]] | None = None
        for side in ("left", "right"):
            hits = [a["seq"] for a in recent if self._flank_side(a, team) == side]
            now = len(hits) / len(recent)
            was = sum(self._flank_side(a, team) == side for a in before) / len(before)
            ratio = now / max(was, 0.05)
            if ratio >= p.flank_ratio and (best is None or ratio > best[0]):
                best = (ratio, side, was, hits)
        if best is None:
            return None
        ratio, side, was, hits = best
        facts = {**self._team_facts(team), "side": side, "side_tr": SIDE_TR[side], "share_now_pct": round(100 * len(hits) / len(recent)),
                 "share_before_pct": round(100 * was), "recent_min": round(p.flank_window_s / 60)}
        return self._make(t, "flank_overload", team, facts, hits, ratio / 3, key=key)

    # ------------------------------------------------------------------ physical rows
    def _on_physical(self, t: float, row: dict) -> list[dict]:
        p, pid = self.p, row["player_id"]
        rows = self._phys.setdefault(pid, [])
        rows.append((row["minute"], row["hsr_m"]))
        key = ("physical_drop", pid)
        if len(rows) < p.phys_min_earlier + p.phys_recent_min or not self._ready(key, t, "physical_drop"):
            return []
        recent = [h for _, h in rows[-p.phys_recent_min:]]
        earlier = [h for _, h in rows[: -p.phys_recent_min]]
        was = sum(earlier) / len(earlier)
        if was < p.phys_min_hsr:
            return []
        ratio = (sum(recent) / len(recent)) / was
        if ratio > p.phys_ratio:
            return []
        mine = [s for ts, s in self._by_player.get(pid, []) if ts > t - 60.0 * p.phys_recent_min]  # his own actions, if any
        facts = {**self._team_facts(row["team"]), "player": self.names[pid], "hsr_now_pct": round(100 * ratio),
                 "recent_min": p.phys_recent_min}
        return [self._make(t, "physical_drop", row["team"], facts, mine, 0.5 + (1 - ratio), player_id=pid, key=key)]

    # ------------------------------------------------------------------ milestones
    def _goal(self, ev: dict) -> dict:
        team = ev["team"]
        self._score[team] += 1
        shot = self._last_shot.get(team)
        scorer = ev.get("player_id") or (shot or {}).get("player_id")
        # No opponent name: a goal sentence names the scorer's team only, so "1-0 to <the wrong team>" cannot pass the Verifier.
        facts = {**self._team_facts(team, opponent=False), "player": self.names.get(scorer, ""), "home_score": self._score["HOME"],
                 "away_score": self._score["AWAY"]}
        evidence = [ev["seq"]] + ([shot["seq"]] if shot else [])
        return self._make(ev["t"], "goal", team, facts, sorted(evidence), 1.0, player_id=scorer)

    def _shot_chance(self, ev: dict) -> dict:
        self._last_shot_chance = ev["t"]
        facts = {**self._team_facts(ev["team"]), "source": "shot", "player": self.names.get(ev.get("player_id") or "", ""),
                 "outcome": ev.get("outcome") or ""}
        return self._make(ev["t"], "chance", ev["team"], facts, [ev["seq"]], 1.0, player_id=ev.get("player_id"))

    def _on_packet(self, pk: dict) -> list[dict]:
        t = pk["t"]
        if (not pk["in_play"] or pk["danger"] < self.p.danger_threshold or t - self._last_danger_chance < self.p.danger_cooldown_s
                or t - self._last_shot_chance < self.p.shot_quiet_s):
            return []
        self._last_danger_chance = t
        facts = {**self._team_facts(pk["team"]), "source": "danger"}  # no danger value: the sound already carries it
        return [self._make(t, "chance", pk["team"], facts, [self._last_seq], pk["danger"])]
