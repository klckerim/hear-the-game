"""Validate synthetic matches against the real data they were calibrated on, and check that every
hidden scenario leaves a measurable trace (otherwise no detector could ever find it).

Writes data/synthetic/validation.md and data/synthetic/validation.png.

Run: python -m htg.validate
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from htg.generate import OUT_DIR, sample_hist
from htg.pitch import GRID_X, to_attacking

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAL = json.loads((ROOT / "data" / "calibration" / "calibration.json").read_text())


def load(d: Path):
    ev = pd.DataFrame([json.loads(line) for line in (d / "events.jsonl").open()])
    ball = pd.read_parquet(d / "ball.parquet")
    phys = pd.DataFrame([json.loads(line) for line in (d / "physical.jsonl").open()])
    truth = json.loads((d / "truth.json").read_text())["scenarios"]
    return ev, ball, phys, truth


def real_sample(hist, n, rng):
    return np.array([sample_hist(hist, rng) for _ in range(n)])


def distributions(matches, rng):
    sb, sc = CAL["statsbomb"], CAL["skillcorner"]
    pass_len, gaps, speeds = [], [], []
    for ev, ball, _, _ in matches:
        p = ev[ev["type"] == "pass"]
        pass_len += list(np.hypot(p["end"].str["x"] - p["start"].str["x"], p["end"].str["y"] - p["start"].str["y"]))
        onball = ev[ev["type"].isin(["pass", "carry", "shot"])]
        for _, g in onball.groupby("possession_id"):
            d = np.diff(g["t"].to_numpy())
            gaps += list(d[(d > 0) & (d < 20)])
        b = ball[ball["in_play"]]
        v = np.hypot(np.diff(b["x"]), np.diff(b["y"])) * 10
        same = np.diff(b["t"]) < 0.11
        speeds += list(v[same & (v > 2) & (v < 40)])
    rows = []
    for name, syn, hist in [("Pass length (m)", pass_len, sb["pass_length_m"]["hist"]),
                            ("Time between on-ball actions (s)", gaps, sb["action_gap_s"]["hist"]),
                            ("Moving ball speed (m/s)", speeds, sc["ball_speed_moving_mps"]["hist"])]:
        real = real_sample(hist, 5000, rng)
        syn = np.asarray(syn)
        ks = ks_2samp(syn, real)
        rows.append({"metric": name, "real_median": np.median(real), "synthetic_median": np.median(syn),
                     "ks": ks.statistic, "syn": syn, "real": real})
    return rows


def occupancy(matches):
    real = np.array(CAL["statsbomb"]["zone_occupancy"]).reshape(GRID_X, -1).sum(1)
    syn = np.zeros(GRID_X)
    for ev, *_ in matches:
        for _, e in ev[ev["type"].isin(["pass", "carry", "shot"])].iterrows():
            xa, _ = to_attacking(e["start"]["x"], e["start"]["y"], e["team"])
            syn[min(GRID_X - 1, int(xa / 105 * GRID_X))] += 1
    return real, syn / syn.sum()


def scenario_signal(ev, phys, s):
    """Effect size of a scenario on the statistic a detector would watch: inside window vs rest of the match."""
    inside = (ev["t"] >= s["start"]) & (ev["t"] < s["end"])
    team = s["team"]
    if s["type"] == "press_increase":
        opp_actions = ev[(ev["team"] != team) & ev["type"].isin(["pass", "carry"])]
        def rate(mask):
            return opp_actions[mask.reindex(opp_actions.index)]["under_pressure"].fillna(False).mean()
        return "share of opponent actions under pressure", rate(inside), rate(~inside)
    if s["type"] == "tempo_drop":
        own = ev[(ev["team"] == team) & ev["type"].isin(["pass", "carry", "shot"])]
        def gap(mask):
            g = own[mask.reindex(own.index)]
            d = g.groupby("possession_id")["t"].diff().dropna()
            return d[(d > 0) & (d < 20)].median()
        return "median seconds between own actions", gap(inside), gap(~inside)
    if s["type"] == "flank_overload":
        own = ev[(ev["team"] == team) & (ev["type"] == "pass")]
        ya = np.where(own["team"] == "HOME", own["end"].str["y"], 68 - own["end"].str["y"])
        flank = (ya > 42.5) if s["params"]["side"] == "left" else (ya < 25.5)
        flank = pd.Series(flank, index=own.index)
        m = inside.reindex(own.index)
        return f"share of passes to the {s['params']['side']} flank", flank[m].mean(), flank[~m].mean()
    if s["type"] == "fatigue":
        p = phys[phys["player_id"] == s["player_id"]]
        after = p[p["minute"] * 60 >= s["start"] + 300]["hsr_m"].mean()
        before = p[p["minute"] * 60 < s["start"]]["hsr_m"].mean()
        return "high-speed running metres per minute", after, before
    return "", np.nan, np.nan


def main():
    rng = np.random.default_rng(0)
    dirs = sorted(OUT_DIR.glob("match_*"))
    matches = [load(d) for d in dirs]
    n = len(matches)
    sb = CAL["statsbomb"]["per_match"]
    per = {k: np.mean([(ev["type"] == t).sum() for ev, *_ in matches]) for k, t in
           [("passes", "pass"), ("carries", "carry"), ("shots", "shot"), ("goals", "goal")]}
    dist = distributions(matches, rng)
    real_occ, syn_occ = occupancy(matches)
    occ_corr = float(np.corrcoef(real_occ, syn_occ)[0, 1])

    sig_rows = []
    for d, (ev, _, phys, truth) in zip(dirs, matches, strict=True):
        for s in truth:
            stat, inside, outside = scenario_signal(ev, phys, s)
            sig_rows.append((d.name, s["id"], s["type"], s["team"], stat, inside, outside))

    lines = ["# Synthetic data validation", "",
             f"{n} synthetic matches vs. calibration source data "
             f"({CAL['statsbomb']['source']}; {CAL['skillcorner']['source']}).", "",
             "## Per match", "", "| Metric | Real | Synthetic | Ratio |", "|---|---|---|---|"]
    for k in ("passes", "carries", "shots", "goals"):
        lines.append(f"| {k} | {sb[k]:.1f} | {per[k]:.1f} | {per[k] / sb[k]:.2f} |")
    lines += ["", "## Distributions", "",
              "KS statistic: 0 = identical distributions, below ~0.1 = close.", "",
              "| Metric | Real median | Synthetic median | KS |", "|---|---|---|---|"]
    for r in dist:
        lines.append(f"| {r['metric']} | {r['real_median']:.2f} | {r['synthetic_median']:.2f} | {r['ks']:.3f} |")
    lines += ["", f"Action location along the pitch (12 bands): correlation real vs synthetic = {occ_corr:.3f}", "",
              "## Hidden scenarios leave a measurable trace", "",
              "Inside = during the scenario window, outside = rest of the match.", "",
              "| Match | Scenario | Team | Statistic | Inside | Outside | Change |", "|---|---|---|---|---|---|---|"]
    changes = {}
    for m, sid, ty, team, stat, a, b in sig_rows:
        ch = (a - b) / b if b else np.nan
        changes.setdefault(ty, []).append(ch)
        lines.append(f"| {m} | {sid} {ty} | {team} | {stat} | {a:.3f} | {b:.3f} | {ch:+.0%} |")
    lines += ["", "Median change by scenario type: " +
              ", ".join(f"{k} {np.nanmedian(v):+.0%}" for k, v in changes.items()), ""]
    (OUT_DIR / "validation.md").write_text("\n".join(lines))

    fig, ax = plt.subplots(1, 4, figsize=(16, 3.4))
    for a, r in zip(ax, dist, strict=False):
        hi = np.quantile(r["real"], 0.98)
        bins = np.linspace(0, hi, 40)
        a.hist(r["real"], bins=bins, density=True, alpha=0.5, label="real", color="#3b6ea5")
        a.hist(r["syn"], bins=bins, density=True, histtype="step", lw=2, label="synthetic", color="#d0582f")
        a.set_title(f"{r['metric']}\nKS {r['ks']:.3f}", fontsize=9)
        a.legend(fontsize=8)
    ax[3].bar(np.arange(GRID_X) - 0.2, real_occ, 0.4, label="real", color="#3b6ea5")
    ax[3].bar(np.arange(GRID_X) + 0.2, syn_occ, 0.4, label="synthetic", color="#d0582f")
    ax[3].set_title(f"Action location along pitch (own goal -> opp. goal)\ncorr {occ_corr:.3f}", fontsize=9)
    ax[3].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "validation.png", dpi=120)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
