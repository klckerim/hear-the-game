"""Learn the statistics the synthetic generator needs from real open data.

Inputs (data/raw, not committed, see scripts/download_data.sh):
    StatsBomb Open Data, Premier League 2015/16 event files
    SkillCorner Open Data, A-League 2024/25 broadcast tracking (10 fps)

Output (committed): data/calibration/calibration.json
    Only aggregated statistics are written. No raw event or tracking rows leave data/raw.

Run: python -m htg.calibrate
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from htg.pitch import GRID_X, GRID_Y, LENGTH, WIDTH, from_statsbomb, zone_of

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "calibration" / "calibration.json"
NZ = GRID_X * GRID_Y

MOVE_TYPES = {"Pass", "Carry"}
LOSS_TYPES = {"Dispossessed", "Miscontrol"}


def _loc(ev, key="location"):
    loc = ev.get(key)
    return from_statsbomb(*loc[:2]) if loc else None


def statsbomb_stats(event_dir: Path) -> dict:
    files = sorted(event_dir.glob("*.json"))
    counts = {k: np.zeros(NZ) for k in ("move", "shot", "loss", "total", "pressured", "goal", "pass_att")}
    trans = np.zeros((NZ, NZ))          # successful move origin -> destination (passes and carries, for xT)
    trans_pass = np.zeros((NZ, NZ))     # pass origin -> intended destination (all attempts)
    carry_vec = []                      # carry displacement (dx, dy) in the attacking frame
    pass_len, carry_len, gaps = [], [], []
    pass_ok = defaultdict(lambda: [0, 0])  # zone -> [successes, attempts]
    xg_sum = np.zeros(NZ)
    per_match = Counter()

    for f in files:
        events = json.loads(f.read_text())
        prev_t, prev_poss = None, None
        for ev in events:
            ty = ev["type"]["name"]
            if ty not in MOVE_TYPES | LOSS_TYPES | {"Shot"}:
                continue
            p = _loc(ev)
            if p is None:
                continue
            z = zone_of(*p)
            hh, mm, ss = ev["timestamp"].split(":")
            t = ev["period"] * 10_000 + int(hh) * 3600 + int(mm) * 60 + float(ss)  # period offset keeps halves apart
            poss = ev.get("possession")
            if prev_poss == poss and prev_t is not None and 0 < t - prev_t < 20:
                gaps.append(t - prev_t)
            prev_t, prev_poss = t, poss

            counts["total"][z] += 1
            if ev.get("under_pressure"):
                counts["pressured"][z] += 1

            if ty == "Shot":
                counts["shot"][z] += 1
                xg_sum[z] += ev["shot"].get("statsbomb_xg", 0.0)
                per_match["shots"] += 1
                if ev["shot"]["outcome"]["name"] == "Goal":
                    counts["goal"][z] += 1
                    per_match["goals"] += 1
                continue
            if ty in LOSS_TYPES:
                counts["loss"][z] += 1
                continue

            key = "pass" if ty == "Pass" else "carry"
            end = _loc(ev[key], "end_location")
            if end is None:
                continue
            length = float(np.hypot(end[0] - p[0], end[1] - p[1]))
            success = ty == "Carry" or "outcome" not in ev["pass"]
            if ty == "Pass":
                counts["pass_att"][z] += 1
                trans_pass[z, zone_of(*end)] += 1
                per_match["passes"] += 1
                pass_ok[z][1] += 1
                pass_len.append(length)
                if success:
                    pass_ok[z][0] += 1
            elif length > 0.5:
                carry_len.append(length)
                carry_vec.append((end[0] - p[0], end[1] - p[1]))
                per_match["carries"] += 1
            if success:
                counts["move"][z] += 1
                trans[z, zone_of(*end)] += 1
            else:
                counts["loss"][z] += 1

    n_matches = len(files)
    total = np.maximum(counts["total"], 1)
    p_shot = counts["shot"] / total
    p_move = counts["move"] / total  # successful moves only, used by xT
    # Generator action model: on each touch a player shoots, attempts a move (pass or carry), or is dispossessed.
    attempts = counts["pass_att"] + (counts["move"] - _succ_pass(counts, pass_ok))
    gen_shot = counts["shot"] / total
    gen_move = np.clip(attempts / total, 0, 1)
    gen_loss = np.clip(1 - gen_shot - gen_move, 0, 1)
    p_loss = 1.0 - p_shot - p_move
    cv = np.array(carry_vec)
    carry_h, cx, cy = np.histogram2d(cv[:, 0], cv[:, 1], bins=24, range=[[-30, 30], [-30, 30]])
    xg_zone = np.where(counts["shot"] > 0, xg_sum / np.maximum(counts["shot"], 1), 0)
    trans_p = trans / np.maximum(trans.sum(1, keepdims=True), 1)

    # Expected Threat (Karun Singh): xT = p_shot * xG + p_move * T @ xT, iterated to convergence
    xt = np.zeros(NZ)
    for _ in range(30):
        xt = p_shot * xg_zone + p_move * (trans_p @ xt)

    return {
        "source": f"StatsBomb Open Data, Premier League 2015/16, {n_matches} matches",
        "n_matches": n_matches,
        "zone_probs": {"shot": p_shot.round(4).tolist(), "move": p_move.round(4).tolist(),
                       "loss": np.clip(p_loss, 0, 1).round(4).tolist()},
        "action_probs": {"shot": gen_shot.round(4).tolist(), "move_attempt": gen_move.round(4).tolist(),
                         "dispossessed": gen_loss.round(4).tolist()},
        "pass_transition": (trans_pass / np.maximum(trans_pass.sum(1, keepdims=True), 1)).round(5).tolist(),
        "carry_displacement": {"edges_dx": cx.round(2).tolist(), "edges_dy": cy.round(2).tolist(),
                               "p": (carry_h / carry_h.sum()).round(6).tolist()},
        "pressured_rate": (counts["pressured"] / total).round(4).tolist(),
        "zone_occupancy": (counts["total"] / counts["total"].sum()).round(5).tolist(),
        "xg_by_zone": xg_zone.round(4).tolist(),
        "transition": trans_p.round(5).tolist(),
        "xt": xt.round(5).tolist(),
        "pass_success_by_zone": [round(s / a, 4) if a else 0.75 for s, a in (pass_ok[z] for z in range(NZ))],
        "pass_length_m": _quantiles(pass_len),
        "carry_length_m": _quantiles(carry_len),
        "action_gap_s": _quantiles(gaps),
        "per_match": {k: round(v / n_matches, 2) for k, v in per_match.items()},
    }


def skillcorner_stats(sc_dir: Path) -> dict:
    speeds, possession_runs = [], []
    n = 0
    for f in sorted(sc_dir.glob("*/tracking.jsonl")):
        n += 1
        prev, run_group, run_len = None, None, 0
        with f.open() as fh:
            for line in fh:
                fr = json.loads(line)
                b = fr["ball_data"]
                g = (fr.get("possession") or {}).get("group")
                if b["x"] is None or fr["period"] is None:
                    prev = None
                    continue
                if prev is not None:
                    v = float(np.hypot(b["x"] - prev[0], b["y"] - prev[1]) * 10)  # 10 fps -> m/s
                    if v < 40:
                        speeds.append(v)
                prev = (b["x"], b["y"])
                if g == run_group:
                    run_len += 1
                else:
                    if run_group is not None and run_len > 5:
                        possession_runs.append(run_len / 10)
                    run_group, run_len = g, 1
    speeds = np.array(speeds)
    moving = speeds[speeds > 2.0]
    return {
        "source": f"SkillCorner Open Data, A-League 2024/25 broadcast tracking, {n} matches",
        "n_matches": n,
        "ball_speed_moving_mps": _quantiles(moving),
        "possession_duration_s": _quantiles(possession_runs),
    }


ROLE_GROUP = {"GK": None, "FB": "Full Back", "CB": "Central Defender", "CM": "Midfield",
              "W": "Wide Attacker", "ST": "Center Forward"}


def _succ_pass(counts, pass_ok):
    """Successful passes per zone (counts['move'] holds successful passes + carries)."""
    return np.array([pass_ok[z][0] for z in range(NZ)], dtype=float)


def physical_stats(csv_path: Path) -> dict:
    """Per-role physical baselines from SkillCorner season aggregates.

    Rows are per-player season averages per match (only performances above 60 minutes are included upstream).
    """
    import pandas as pd

    d = pd.read_csv(csv_path)
    d = d[d["count_match"] >= 3]
    out = {}
    for role, group in ROLE_GROUP.items():
        g = d[d["position_group"] == group] if group else d[d["position_group"] == "Central Defender"]
        mins = g["minutes_full_all"]
        stats = {
            "metres_per_min": round(float(g["total_metersperminute_full_all"].median()), 2),
            "hsr_m_per_min": round(float((g["hsr_distance_full_all"] / mins).median()), 3),
            "sprints_per_90": round(float((g["sprint_count_full_all"] / mins * 90).median()), 2),
            "psv99_kmh": round(float(g["psv99"].median()), 2),
        }
        if role == "GK":  # no keeper rows in the file; scale outfield CB values down (assumption, documented)
            stats = {"metres_per_min": round(stats["metres_per_min"] * 0.55, 2), "hsr_m_per_min": 0.3,
                     "sprints_per_90": 1.0, "psv99_kmh": round(stats["psv99_kmh"] * 0.85, 2), "assumed": True}
        out[role] = stats
    return {"source": f"SkillCorner Open Data, A-League 2024/25 physical aggregates, {len(d)} players", "roles": out}


def _quantiles(values) -> dict:
    a = np.asarray(values, dtype=float)
    qs = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
    return {"n": int(a.size), "mean": round(float(a.mean()), 3),
            "q": {str(q): round(float(np.quantile(a, q)), 3) for q in qs},
            "hist": _hist(a)}


def _hist(a, bins=40):
    hi = float(np.quantile(a, 0.99))
    counts, edges = np.histogram(a[a <= hi], bins=bins)
    return {"edges": edges.round(3).tolist(), "p": (counts / counts.sum()).round(5).tolist()}


def main():
    cal = {
        "grid": [GRID_X, GRID_Y], "pitch": [LENGTH, WIDTH], "frame": "attacking (team in possession attacks +x)",
        "statsbomb": statsbomb_stats(RAW / "statsbomb" / "events"),
        "skillcorner": skillcorner_stats(RAW / "skillcorner"),
        "physical": physical_stats(RAW / "skillcorner" / "physical_aggregates.csv"),
    }
    sb_counts = cal["statsbomb"]
    sb_counts["p_pass_given_move"] = round(
        sb_counts["pass_length_m"]["n"] / (sb_counts["pass_length_m"]["n"] + sb_counts["carry_length_m"]["n"]), 4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cal, indent=1))
    sb, sc = cal["statsbomb"], cal["skillcorner"]
    print(f"wrote {OUT}")
    print(f"  StatsBomb: {sb['n_matches']} matches, per match {sb['per_match']}")
    print(f"  pass length median {sb['pass_length_m']['q']['0.5']} m, action gap median {sb['action_gap_s']['q']['0.5']} s")
    print(f"  max xT {max(sb['xt']):.3f}")
    print(f"  SkillCorner: {sc['n_matches']} matches, moving ball speed median {sc['ball_speed_moving_mps']['q']['0.5']} m/s,"
          f" possession median {sc['possession_duration_s']['q']['0.5']} s")


if __name__ == "__main__":
    main()
