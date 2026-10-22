"""Seeded synthetic match generator, calibrated on real open data.

Every match is a Markov process over a 12x8 zone grid in the attacking frame:
each on-ball action is a shot, a move (pass or carry) or a loss, with probabilities,
destinations, pass lengths, timing and ball speeds taken from data/calibration/calibration.json.

Hidden tactical scenarios are injected and written to truth.json, so detectors and
narration can later be scored against known ground truth:
    press_increase  - a team presses harder for a period
    tempo_drop      - a team slows its possession play
    flank_overload  - a team pushes its play down one flank
    fatigue         - one player's physical output drops for the rest of the match

Outputs, per match, in data/synthetic/match_<seed>/:
    meta.json       teams, rosters, seed, calibration version
    events.jsonl    raw event feed (schemas/event.schema.json)
    ball.parquet    10 Hz ball track (t, x, y, in_play, team, period)
    physical.jsonl  per-player, per-minute physical output (distance, HSR, sprints, top speed)
    truth.json      injected scenarios (never shown to the detectors)

Run: python -m htg.generate --seeds 1 2 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from htg.pitch import LENGTH, WIDTH, sample_in_zone, to_global, zone_of

ROOT = Path(__file__).resolve().parents[1]
CAL_PATH = ROOT / "data" / "calibration" / "calibration.json"
OUT_DIR = ROOT / "data" / "synthetic"
HALF = 2700.0
HZ = 10
# Zone-level probabilities come straight from StatsBomb. The Markov chain slightly over-visits the box
# (no defensive shape is modelled), so shot propensity is scaled once, fitted by simulation so that
# shots per match match the real data (see htg/validate.py).
SHOT_SCALE = 0.45
# Share of dispossessions that end in a foul and a free kick. Fouls and longer set-piece pauses bring
# ball-in-play time to a realistic ~55-60 of 90 minutes.
FOUL_SHARE = 0.45
# Synthetic shots come from slightly better zones than real ones, so conversion is scaled once
# (fitted by simulation) to keep goals per match realistic.
FINISH_SCALE = 0.85

# Fictional squads. Anchors are attacking-frame positions (left flank = high y).
# Club names are fictional (no professional club uses them) and never feed the RNG: renaming does not change the match.
ROLES = [("GK", 5, 34), ("FB", 30, 58), ("CB", 25, 44), ("CB", 25, 24), ("FB", 30, 10),
         ("CM", 48, 46), ("CM", 44, 34), ("CM", 48, 22), ("W", 74, 58), ("ST", 82, 34), ("W", 74, 10)]
SQUADS = {
    "HOME": {"name": {"tr": "Northport", "en": "Northport"}, "color": "red",
             "players": ["Usta", "Aksoy", "Demir", "Toprak", "Kurt", "Kaya", "Polat", "Erdem", "Şahin", "Arda", "Yıldız"]},
    "AWAY": {"name": {"tr": "Valemont", "en": "Valemont"}, "color": "blue",
             "players": ["Novak", "Moreau", "Haddad", "Lindqvist", "Costa", "Silva", "Mensah", "Ito", "Baptiste", "Okafor", "Rossi"]},
}
OTHER = {"HOME": "AWAY", "AWAY": "HOME"}


def roster(team: str) -> list[dict]:
    prefix = "H" if team == "HOME" else "A"
    return [{"player_id": f"{prefix}{i + 1:02d}", "name": name, "role": ROLES[i][0],
             "anchor": [ROLES[i][1], ROLES[i][2]]}
            for i, name in enumerate(SQUADS[team]["players"])]


# ---------------------------------------------------------------- calibration helpers
class Cal:
    def __init__(self, path: Path = CAL_PATH):
        raw = path.read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()[:12]
        c = json.loads(raw)
        sb, sc = c["statsbomb"], c["skillcorner"]
        self.p_shot = np.array(sb["action_probs"]["shot"])
        self.p_move = np.array(sb["action_probs"]["move_attempt"])
        self.p_loss = np.array(sb["action_probs"]["dispossessed"])
        self.pressured = np.array(sb["pressured_rate"])
        self.xg = np.array(sb["xg_by_zone"])
        self.trans = np.array(sb["pass_transition"])
        cd = sb["carry_displacement"]
        self.carry_p = np.array(cd["p"]).ravel()
        self.carry_p = self.carry_p / self.carry_p.sum()  # undo rounding in the JSON
        self.carry_dx, self.carry_dy = np.array(cd["edges_dx"]), np.array(cd["edges_dy"])
        self.pass_ok = np.array(sb["pass_success_by_zone"])
        self.p_pass = sb["p_pass_given_move"]
        self.gap = sb["action_gap_s"]["hist"]
        self.carry_len = sb["carry_length_m"]["hist"]
        self.ball_speed = sc["ball_speed_moving_mps"]["hist"]
        self.physical = c["physical"]["roles"]


def sample_hist(h: dict, rng: np.random.Generator, lo: float = -math.inf, hi: float = math.inf) -> float:
    edges, p = np.array(h["edges"]), np.array(h["p"], dtype=float)
    mask = (edges[1:] > lo) & (edges[:-1] < hi)
    p = np.where(mask, p, 0.0)
    if p.sum() == 0:
        return float(np.clip((edges[0] + edges[-1]) / 2, lo, hi))
    i = rng.choice(len(p), p=p / p.sum())
    a, b = max(edges[i], lo), min(edges[i + 1], hi)
    return float(a + rng.random() * (b - a))


# ---------------------------------------------------------------- scenarios
def draw_scenarios(rng: np.random.Generator, rosters: dict) -> list[dict]:
    m = 60.0
    s = []
    t1 = rng.uniform(10, 25) * m
    press_team = str(rng.choice(["HOME", "AWAY"]))
    s.append({"id": "S1", "type": "press_increase", "team": press_team, "start": round(t1), "end": round(t1 + 12 * m),
              "params": {"factor": 1.9}, "describe": f"{press_team} presses much harder (out of possession)"})
    t2 = t1 + 12 * m + rng.uniform(4, 8) * m
    side = str(rng.choice(["left", "right"]))
    flank_team = str(rng.choice(["HOME", "AWAY"]))
    s.append({"id": "S2", "type": "flank_overload", "team": flank_team, "start": round(t2), "end": round(t2 + 10 * m),
              "params": {"side": side, "bias": 4.0}, "describe": f"{flank_team} pushes play down its {side} flank"})
    t3 = rng.uniform(52, 62) * m
    tempo_team = str(rng.choice(["HOME", "AWAY"]))
    s.append({"id": "S3", "type": "tempo_drop", "team": tempo_team, "start": round(t3), "end": round(t3 + 10 * m),
              "params": {"factor": 1.8}, "describe": f"{tempo_team} slows its possession play"})
    team = str(rng.choice(["HOME", "AWAY"]))
    cands = [p for p in rosters[team] if p["role"] in ("FB", "CM", "W")]
    player = cands[int(rng.integers(len(cands)))]
    t4 = rng.uniform(62, 72) * m
    s.append({"id": "S4", "type": "fatigue", "team": team, "player_id": player["player_id"], "start": round(t4),
              "end": 5400, "params": {"factor": 0.55}, "describe": f"{player['name']} ({team}) tires"})
    return s


@dataclass
class Mods:
    press: float = 1.0      # pressure multiplier applied by the defending team
    tempo: float = 1.0      # action gap multiplier for the team in possession
    shot: float = 1.0
    back_bias: float = 1.0  # weight for backward destinations
    flank: tuple | None = None
    fatigue: float = 1.0    # actor's physical / technical factor (1 = fresh)


def active_mods(scen: list[dict], t: float, team: str, actor_id: str) -> Mods:
    m = Mods()
    for s in scen:
        if not (s["start"] <= t < s["end"]):
            continue
        if s["type"] == "press_increase" and s["team"] == OTHER[team]:
            m.press = s["params"]["factor"]
        elif s["type"] == "tempo_drop" and s["team"] == team:
            m.tempo, m.shot, m.back_bias = s["params"]["factor"], 0.6, 1.6
        elif s["type"] == "flank_overload" and s["team"] == team:
            m.flank = (s["params"]["side"], s["params"]["bias"])
        elif s["type"] == "fatigue" and s.get("player_id") == actor_id:
            ramp = min(1.0, (t - s["start"]) / 300.0)  # fatigue builds over five minutes
            m.fatigue = 1.0 - ramp * (1.0 - s["params"]["factor"])
    return m


# ---------------------------------------------------------------- the match
@dataclass
class Match:
    seed: int
    cal: Cal
    duration: float = 5400.0
    rng: np.random.Generator = field(init=False)

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.match_id = f"synth_{self.seed:04d}"
        self.rosters = {t: roster(t) for t in ("HOME", "AWAY")}
        self.scenarios = draw_scenarios(self.rng, self.rosters)
        self.events: list[dict] = []
        self.keys: list[tuple] = []  # (t, x, y, in_play, team, teleport) in global frame
        self.poss_id = 0

    # --- helpers
    def emit(self, t, ty, team, player=None, start=None, end=None, **kw):
        ev = {"match_id": self.match_id, "seq": len(self.events), "t": round(float(t), 2),
              "period": 1 if t < HALF else 2, "type": ty, "team": team,
              "player_id": player["player_id"] if player else None,
              "possession_id": self.poss_id}
        if start is not None:  # start/end are given in the attacking frame of `team`
            gx, gy = to_global(*start, team)
            ev["start"] = {"x": round(float(np.clip(gx, 0, LENGTH)), 2), "y": round(float(np.clip(gy, 0, WIDTH)), 2)}
        if end is not None:
            gx, gy = to_global(*end, team)
            ev["end"] = {"x": round(float(np.clip(gx, 0, LENGTH)), 2), "y": round(float(np.clip(gy, 0, WIDTH)), 2)}
        for k, v in kw.items():
            ev[k] = round(v, 2) if isinstance(v, float) else v
        self.events.append(ev)
        return ev

    def key(self, t, pos_att, team, in_play=True, teleport=False):
        gx, gy = to_global(*pos_att, team)
        self.keys.append((float(t), float(np.clip(gx, 0, LENGTH)), float(np.clip(gy, 0, WIDTH)), in_play, team, teleport))

    def pick(self, team: str, pos_att, attacking: bool, exclude_gk: bool = True) -> dict:
        """Player most likely to be on the ball (attacking) or closest to it (defending)."""
        bx, by = pos_att if attacking else (LENGTH - pos_att[0], WIDTH - pos_att[1])
        shift = 0.4 * (bx - 52.5)
        w = []
        for p in self.rosters[team]:
            ax, ay = p["anchor"]
            d2 = (ax + shift - bx) ** 2 + (ay - by) ** 2
            gk_ok = p["role"] != "GK" or (bx < 18 and not exclude_gk)
            w.append(math.exp(-d2 / (2 * 14.0 ** 2)) if gk_ok else 0.0)
        w = np.array(w) + 1e-9
        return self.rosters[team][int(self.rng.choice(len(w), p=w / w.sum()))]

    def keeper(self, team):
        return self.rosters[team][0]

    # --- restarts
    def restart(self, t_stop, pos_stop_att, team_stop, kind, new_team, new_pos_att, dead):
        self.key(t_stop, pos_stop_att, team_stop, in_play=False)
        t = t_stop + dead
        if t >= HALF > t_stop:
            t = HALF + 0.0
        self.poss_id += 1
        self.key(t, new_pos_att, new_team, in_play=True, teleport=True)
        player = self.keeper(new_team) if kind in ("goal_kick", "keeper") else self.pick(new_team, new_pos_att, True)
        self.emit(t, "restart" if kind != "kickoff" else "kickoff", new_team, player, new_pos_att, restart=kind)
        return t, new_team, new_pos_att

    def turnover(self, t, pos_att, team):
        """Ball won by the opponent at pos_att (given in the losing team's frame)."""
        new_team = OTHER[team]
        new_pos = (LENGTH - pos_att[0], WIDTH - pos_att[1])
        self.poss_id += 1
        winner = self.pick(new_team, new_pos, True, exclude_gk=new_pos[0] > 16)
        self.emit(t, "ball_recovery", new_team, winner, new_pos, outcome="won")
        self.key(t, new_pos, new_team)
        return new_team, new_pos

    # --- main loop
    def run(self):
        c, rng = self.cal, self.rng
        team, pos, t = "HOME", (52.5, 34.0), 0.0
        self.last_travel = 0.0
        self.key(0, pos, team)
        self.emit(0, "kickoff", team, self.pick(team, pos, True), pos, restart="kickoff")
        second_half_started = False

        while t < self.duration:
            if not second_half_started and t >= HALF:
                self.emit(HALF - 0.01, "period_end", team)
                second_half_started = True
                t, team, pos = self.restart(HALF - 0.01, pos, team, "kickoff", "AWAY", (52.5, 34.0), 0.01)
                continue

            actor = self.pick(team, pos, True, exclude_gk=pos[0] > 16)
            mods = active_mods(self.scenarios, t, team, actor["player_id"])
            # StatsBomb logs an action at the moment of touch: after a pass the next action starts at reception,
            # after a carry it starts where the carry ends. Holding the ball shows up as short extra delays,
            # drawn from the short end of the real gap distribution (scaled by the tempo scenario).
            hold = sample_hist(c.gap, rng, 0.0, 1.2) * 0.25 if self.last_travel else sample_hist(c.gap, rng, 0.2, 4.0)
            t += hold * mods.tempo + 0.8 * (mods.tempo - 1.0)  # a slowed team also takes longer on every touch
            self.last_travel = 0.0
            z = zone_of(*pos)
            self.key(t, pos, team)

            pressured = bool(rng.random() < min(0.95, c.pressured[z] * mods.press))
            if pressured:
                presser = self.pick(OTHER[team], pos, False)
                self.emit(max(0.0, t - 0.3), "pressure", OTHER[team], presser,
                          (LENGTH - pos[0], WIDTH - pos[1]), duration_s=round(float(rng.uniform(0.5, 1.5)), 2))

            p_loss = c.p_loss[z] * (1.0 + 0.6 * (mods.press - 1.0)) * (1.25 if pressured else 1.0) / mods.fatigue ** 0.5
            p = np.array([c.p_shot[z] * mods.shot * SHOT_SCALE, c.p_move[z], p_loss])
            action = ["shot", "move", "loss"][int(rng.choice(3, p=p / p.sum()))]

            if action == "shot":
                t, team, pos = self._shot(t, pos, team, actor, pressured, z)
            elif action == "loss":
                if rng.random() < FOUL_SHARE:  # challenge stopped by the referee: free kick, possession kept
                    fouler = self.pick(OTHER[team], pos, False)
                    self.emit(t + 0.3, "foul", OTHER[team], fouler, (LENGTH - pos[0], WIDTH - pos[1]))
                    t, team, pos = self.restart(t + 0.3, pos, team, "free_kick", team, pos, rng.uniform(18, 40))
                else:
                    team, pos = self.turnover(t + 0.4, pos, team)
                    t += 0.4
            elif rng.random() < c.p_pass:
                t, team, pos = self._pass(t, pos, team, actor, pressured, z, mods)
            else:
                t, pos = self._carry(t, pos, team, actor, pressured, mods)

        self.emit(self.duration, "period_end", team)
        return self

    def _shot(self, t, pos, team, actor, pressured, z):
        rng = self.rng
        xg = max(self.cal.xg[z], 0.02) * FINISH_SCALE
        target = (LENGTH, 34.0 + rng.normal(0, 2.5))
        speed = float(rng.uniform(18, 30))
        travel = math.dist(pos, target) / speed
        r = rng.random()
        outcome = "goal" if r < xg else "saved" if r < xg + 0.3 else "blocked" if r < xg + 0.55 else "off_target"
        self.emit(t, "shot", team, actor, pos, target, outcome=outcome, under_pressure=pressured,
                  speed_mps=speed)
        t_end = t + travel
        self.key(t_end, target, team)
        if outcome == "goal":
            self.emit(t_end, "goal", team, actor, target)
            return self.restart(t_end, target, team, "kickoff", OTHER[team], (52.5, 34.0), rng.uniform(50, 70))
        if outcome == "saved":
            gk = self.keeper(OTHER[team])
            self.emit(t_end, "save", OTHER[team], gk, (LENGTH - target[0], WIDTH - target[1]))
            if rng.random() < 0.35:
                corner = (LENGTH - 0.5, 0.5 if rng.random() < 0.5 else WIDTH - 0.5)
                self.emit(t_end + 0.5, "out", team, None, target)
                return self.restart(t_end + 0.5, target, team, "corner", team, corner, rng.uniform(25, 40))
            return self.restart(t_end, target, team, "keeper", OTHER[team], (6.0, 34.0), rng.uniform(6, 12))
        if outcome == "blocked":
            loose = (pos[0] + rng.uniform(1, 4), pos[1] + rng.normal(0, 3))
            self.key(t + 0.3, loose, team)
            if rng.random() < 0.35:
                return t + 0.3, team, loose
            new_team, new_pos = self.turnover(t + 0.6, loose, team)
            return t + 0.6, new_team, new_pos
        self.emit(t_end, "out", team, None, target)
        return self.restart(t_end, target, team, "goal_kick", OTHER[team], (5.5, 34 + rng.uniform(-9, 9)),
                            rng.uniform(22, 38))

    def _pass(self, t, pos, team, actor, pressured, z, mods):
        rng, c = self.rng, self.cal
        w = c.trans[z].copy()
        if w.sum() == 0:
            w = np.ones_like(w)
        if mods.back_bias != 1.0:
            back = np.array([(k // 8) < (z // 8) for k in range(len(w))])
            w = np.where(back, w * mods.back_bias, w)
        if mods.flank:
            side, bias = mods.flank
            left = np.array([(k % 8) >= 5 for k in range(len(w))])
            right = np.array([(k % 8) <= 2 for k in range(len(w))])
            w = np.where(left if side == "left" else right, w * bias, w)
        dz = int(rng.choice(len(w), p=w / w.sum()))
        dest = sample_in_zone(dz, rng)
        speed = sample_hist(c.ball_speed, rng, 6.0, 30.0) / mods.tempo ** 0.3
        dist = math.dist(pos, dest)
        travel = dist / speed
        p_ok = c.pass_ok[z] * (0.88 if pressured else 1.0) * (mods.fatigue ** 0.3) / (1.0 + 0.15 * (mods.press - 1.0))
        if rng.random() < p_ok:
            self.emit(t, "pass", team, actor, pos, dest, outcome="complete", under_pressure=pressured,
                      speed_mps=speed, duration_s=round(travel, 2))
            self.key(t + travel, dest, team)
            self.last_travel = travel
            return t + travel, team, dest
        u = float(rng.uniform(0.4, 0.95))
        cut = (pos[0] + u * (dest[0] - pos[0]), pos[1] + u * (dest[1] - pos[1]))
        self.emit(t, "pass", team, actor, pos, dest, outcome="incomplete", under_pressure=pressured,
                  speed_mps=speed, duration_s=round(travel * u, 2))
        t_cut = t + travel * u
        self.key(t_cut, cut, team)
        near_line = dest[1] < 4 or dest[1] > WIDTH - 4 or dest[0] > LENGTH - 3
        if near_line and rng.random() < 0.8:
            out_pt = (min(dest[0], LENGTH), float(np.clip(dest[1], 0, WIDTH)))
            self.key(t + travel, out_pt, team)
            self.emit(t + travel, "out", team, None, out_pt)
            if out_pt[0] >= LENGTH - 2:
                return self.restart(t + travel, out_pt, team, "goal_kick", OTHER[team], (5.5, 34.0), rng.uniform(20, 35))
            opp = (LENGTH - out_pt[0], WIDTH - out_pt[1])
            return self.restart(t + travel, out_pt, team, "throw_in", OTHER[team], opp, rng.uniform(12, 25))
        new_team, new_pos = self.turnover(t_cut + 0.2, cut, team)
        return t_cut + 0.2, new_team, new_pos

    def _carry(self, t, pos, team, actor, pressured, mods):
        rng, c = self.rng, self.cal
        k = int(rng.choice(len(c.carry_p), p=c.carry_p))
        i, j = divmod(k, len(c.carry_dy) - 1)
        dx = c.carry_dx[i] + rng.random() * (c.carry_dx[i + 1] - c.carry_dx[i])
        dy = c.carry_dy[j] + rng.random() * (c.carry_dy[j + 1] - c.carry_dy[j])
        dest = (float(np.clip(pos[0] + dx, 1, LENGTH - 1)), float(np.clip(pos[1] + dy, 1, WIDTH - 1)))
        speed = sample_hist(c.ball_speed, rng, 1.5, 7.0) * mods.fatigue ** 0.5
        dur = math.dist(pos, dest) / speed
        self.emit(t, "carry", team, actor, pos, dest, under_pressure=pressured, speed_mps=speed,
                  duration_s=round(dur, 2))
        self.key(t + dur, dest, team)
        self.last_travel = dur
        return t + dur, dest

    # --- derived streams
    def ball_track(self) -> pd.DataFrame:
        keys = sorted(self.keys, key=lambda k: k[0])
        kt = np.array([k[0] for k in keys])
        times = np.round(np.arange(0, self.duration, 1 / HZ), 1)
        rows = []
        j = 0
        for t in times:
            while j + 1 < len(keys) and kt[j + 1] <= t:
                j += 1
            k0 = keys[j]
            k1 = keys[j + 1] if j + 1 < len(keys) else k0
            if k0[3] and k1[3] and not k1[5] and k1[0] > k0[0]:
                a = (t - k0[0]) / (k1[0] - k0[0])
                x, y = k0[1] + a * (k1[1] - k0[1]), k0[2] + a * (k1[2] - k0[2])
            else:
                x, y = k0[1], k0[2]
            rows.append((t, round(x, 2), round(y, 2), bool(k0[3]), k0[4], 1 if t < HALF else 2))
        return pd.DataFrame(rows, columns=["t", "x", "y", "in_play", "team", "period"])

    def physical(self) -> list[dict]:
        rng, rows = self.rng, []
        for minute in range(int(self.duration // 60)):
            t = minute * 60 + 30
            for team in ("HOME", "AWAY"):
                for p in self.rosters[team]:
                    base = self.cal.physical[p["role"]]
                    f = active_mods(self.scenarios, t, team, p["player_id"]).fatigue
                    sprints = int(rng.poisson(base["sprints_per_90"] / 90 * f ** 2))
                    rows.append({
                        "match_id": self.match_id, "minute": minute, "team": team, "player_id": p["player_id"],
                        "distance_m": round(float(base["metres_per_min"] * rng.normal(1, 0.08) * (0.85 + 0.15 * f)), 1),
                        "hsr_m": round(float(base["hsr_m_per_min"] * rng.gamma(4, 0.25) * f ** 1.5), 1),
                        "sprints": sprints,
                        "top_speed_kmh": round(float(base["psv99_kmh"] * (0.9 + 0.1 * f) * rng.uniform(0.82, 1.0)
                                                     if sprints else base["psv99_kmh"] * rng.uniform(0.6, 0.8) * (0.9 + 0.1 * f)), 1),
                    })
        return rows

    def save(self, out_dir: Path = OUT_DIR):
        d = out_dir / f"match_{self.seed:04d}"
        d.mkdir(parents=True, exist_ok=True)
        meta = {"match_id": self.match_id, "seed": self.seed, "duration_s": self.duration, "hz": HZ,
                "calibration_version": self.cal.version, "synthetic": True,
                "teams": {t: {"name": SQUADS[t]["name"], "color": SQUADS[t]["color"], "attacks_towards_x": 105 if t == "HOME" else 0,
                              "players": self.rosters[t]} for t in ("HOME", "AWAY")}}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        with (d / "events.jsonl").open("w") as fh:
            for e in self.events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        self.ball_track().to_parquet(d / "ball.parquet", index=False)
        with (d / "physical.jsonl").open("w") as fh:
            for r in self.physical():
                fh.write(json.dumps(r) + "\n")
        (d / "truth.json").write_text(json.dumps({"match_id": self.match_id, "scenarios": self.scenarios}, indent=1))
        return d


def generate(seed: int, cal: Cal | None = None, out_dir: Path = OUT_DIR) -> Path:
    return Match(seed, cal or Cal()).run().save(out_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    args = ap.parse_args()
    cal = Cal()
    for s in args.seeds:
        d = generate(s, cal)
        ev = [json.loads(line) for line in (d / "events.jsonl").open()]
        goals = {t: sum(1 for e in ev if e["type"] == "goal" and e["team"] == t) for t in ("HOME", "AWAY")}
        print(f"{d.name}: {len(ev)} events, passes {sum(e['type'] == 'pass' for e in ev)}, "
              f"shots {sum(e['type'] == 'shot' for e in ev)}, score {goals['HOME']}-{goals['AWAY']}")


if __name__ == "__main__":
    main()
