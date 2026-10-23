"""Deterministic segments of play for the live commentator.

A segment ends at a dead ball (out, foul, shot, goal, period end) or once it has run SEGMENT_MAX_S; a shot that scores ends at the
goal event, so "shot" and "goal" are one segment. Its `facts` are everything the commentator may say about it, flat (one value per
key) so the Verifier can check names and numbers against them. Same events in, same segments out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from htg.pitch import LENGTH

SEGMENT_MAX_S = 10.0
MAX_PLAYERS = 4
DEAD_BALL = {"out", "foul", "shot", "goal", "period_end"}
ON_BALL = {"kickoff", "pass", "carry", "shot", "goal", "ball_recovery", "restart"}  # events whose player is "involved" with the ball


@dataclass
class Segment:
    segment_id: str
    t0: float
    t1: float
    goal: bool
    facts: dict = field(default_factory=dict)


def _zone(team: str, x: float) -> str:
    """How far up the pitch the team got: own_half / midfield / final_third (HOME attacks x = 105)."""
    ax = x if team == "HOME" else LENGTH - x
    return "own_half" if ax < LENGTH / 2 else "midfield" if ax < LENGTH * 2 / 3 else "final_third"


def goal_effect(scorers: int, others: int) -> str:
    """What a goal did, from the score after it (the scoring team's goals first): computed here, so the model never has to work out
    whether 1-1 is a lead (it once called an equaliser "Northport lead!")."""
    if scorers == others:
        return "equaliser"
    if scorers < others:
        return "pulls_one_back"
    return "takes_lead" if scorers - 1 == others else "extends_lead"


class Segmenter:
    def __init__(self, meta: dict):
        self.teams = {k: v["name"] for k, v in meta["teams"].items()}
        self.names = {p["player_id"]: p["name"] for t in meta["teams"].values() for p in t["players"]}
        self._evs: list[dict] = []
        self._insight: dict | None = None

    def note_insight(self, insight: dict) -> None:
        """A tactical Insight detected during the current segment; the segment's facts mention it."""
        self._insight = insight

    def step(self, ev: dict, score: dict[str, int]) -> list[Segment]:
        """Feed one event (after the detectors saw it, so `score` includes a goal). Returns the segments it closed (0-2)."""
        out = []
        if self._evs and ev["t"] - self._evs[0]["t"] >= SEGMENT_MAX_S and ev["type"] not in ("goal", "save"):
            out.append(self._close("play_on", score))  # the 10 s are up; this event starts the next segment
        self._evs.append(ev)
        if ev["type"] in DEAD_BALL and not (ev["type"] == "shot" and ev.get("outcome") == "goal"):
            out.append(self._close(ev["type"], score))
        return out

    def _close(self, ended_by: str, score: dict[str, int]) -> Segment:
        evs, ins = self._evs, self._insight
        self._evs, self._insight = [], None
        last = evs[-1]
        on_ball = [e for e in evs if e["type"] in ON_BALL and e.get("team")]
        team = on_ball[-1]["team"] if on_ball else last["team"]
        facts: dict = {"minute": int(last["t"] // 60) + 1, "home_team": self.teams["HOME"]["en"], "away_team": self.teams["AWAY"]["en"],
                       "home_score": score["HOME"], "away_score": score["AWAY"], "team_in_possession": self.teams[team]["en"]}
        players: list[str] = []
        for e in on_ball:
            name = self.names.get(e.get("player_id"))
            if name and e["team"] == team:
                players = [p for p in players if p != name] + [name]
        for i, name in enumerate(players[-MAX_PLAYERS:], 1):
            facts[f"player_{i}"] = name
        facts["pass_count"] = sum(e["type"] == "pass" and e["team"] == team for e in evs)
        xs = [e["start"]["x"] for e in on_ball if e["team"] == team and e.get("start")]
        xs += [e["end"]["x"] for e in on_ball if e["team"] == team and e.get("end")]
        if xs:
            facts["progression"] = max((_zone(team, x) for x in xs), key=["own_half", "midfield", "final_third"].index)
        if evs[0]["type"] == "restart":
            facts["started_with"] = evs[0]["restart"]
        facts["ended_by"] = ended_by
        shot = next((e for e in reversed(evs) if e["type"] == "shot"), None)
        if shot and ended_by in ("shot", "goal"):
            facts["shooter"] = self.names.get(shot.get("player_id"), "")
            facts["shot_outcome"] = shot.get("outcome") or ""
            if shot.get("speed_mps"):
                facts["shot_speed_kmh"] = round(shot["speed_mps"] * 3.6)
        if ended_by == "goal":
            facts["scorer"] = self.names.get(last.get("player_id")) or facts.get("shooter", "")
            facts["scoring_team"] = self.teams[last["team"]]["en"]
            facts["goal_effect"] = goal_effect(score[last["team"]], score["AWAY" if last["team"] == "HOME" else "HOME"])
        if ended_by == "foul":
            facts["fouling_team"] = self.teams[last["team"]]["en"]
            if last.get("card"):
                facts["card"] = last["card"]
                facts["booked_player"] = self.names.get(last.get("player_id"), "")
        if ended_by == "out":
            facts["put_out_by"] = self.teams[last["team"]]["en"]
        if ended_by == "period_end":
            facts["period_ended"] = "half_time" if last["period"] == 1 else "full_time"
        if ins:
            facts["tactical_insight"] = ins["type"]
            facts["tactical_team"] = self.teams[ins["team"]]["en"]
        # After a dead ball the restart is many seconds away (seed 7: 14-28 s after a ball out), so there is time to talk.
        length = SEGMENT_MAX_S if ended_by != "play_on" else last["t"] - evs[0]["t"]
        facts["seconds_available"] = round(min(max(length, 3.0), SEGMENT_MAX_S), 1)
        facts = {k: v for k, v in facts.items() if v != ""}
        return Segment(f"{evs[0]['period']}-{evs[0]['seq']}", evs[0]["t"], last["t"], ended_by == "goal", facts)
