"""Score the detectors against the hidden scenarios in `truth.json` (the only place that reads it).

Replays each match at full speed through engine + detectors. A true positive is an Insight of the matching type and
team (and player for fatigue) with `t` in [start, end + 120 s]. Recall and delay are per scenario; precision is per Insight.

    python -m eval.scenarios --seeds 11-30          # report seeds, writes eval/results/scenarios.md
    python -m eval.scenarios --seeds 1-10 --out -   # tuning seeds, print only
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from htg.engine.detectors import Detectors, Params
from htg.engine.state import StateEngine
from htg.generate import OUT_DIR, generate
from htg.replay import iter_items

SCENARIO_TO_INSIGHT = {
    "press_increase": "pressure_shift", "tempo_drop": "tempo_change", "flank_overload": "flank_overload", "fatigue": "physical_drop",
}
GRACE_S = 120.0
RESULTS = Path(__file__).resolve().parent / "results" / "scenarios.md"


def run_match(match_dir: Path, params: Params | None = None) -> list[dict]:
    """All Insights the detectors emit for one match, in replay order."""
    meta = json.loads((match_dir / "meta.json").read_text())
    engine, detectors = StateEngine.from_calibration(), Detectors(meta, params)
    return [i for item in iter_items(match_dir) for i in detectors.step(item, engine.step(item))]


def hits(insight: dict, scen: dict) -> bool:
    return (insight["type"] == SCENARIO_TO_INSIGHT[scen["type"]] and insight["team"] == scen["team"]
            and insight.get("player_id") == scen.get("player_id") and scen["start"] <= insight["t"] <= scen["end"] + GRACE_S)


def score_match(match_dir: Path, params: Params | None = None) -> dict:
    """Per scenario type: scenarios, detected, delays (s), insights, true_positive_insights. Plus counts of other insight types."""
    truth = json.loads((match_dir / "truth.json").read_text())["scenarios"]
    insights = run_match(match_dir, params)
    out = {ty: {"scenarios": 0, "detected": 0, "delays": [], "insights": 0, "tp": 0} for ty in SCENARIO_TO_INSIGHT}
    for scen in truth:
        r = out[scen["type"]]
        r["scenarios"] += 1
        found = [i["t"] for i in insights if hits(i, scen)]
        if found:
            r["detected"] += 1
            r["delays"].append(min(found) - scen["start"])
    for i in insights:
        for ty, itype in SCENARIO_TO_INSIGHT.items():
            if i["type"] == itype:
                out[ty]["insights"] += 1
                out[ty]["tp"] += any(hits(i, s) for s in truth if s["type"] == ty)
    others: dict[str, int] = {}
    for i in insights:
        if i["type"] not in SCENARIO_TO_INSIGHT.values():
            others[i["type"]] = others.get(i["type"], 0) + 1
    return {"types": out, "others": others}


def evaluate(seeds: list[int], params: Params | None = None) -> str:
    total = {ty: {"scenarios": 0, "detected": 0, "delays": [], "insights": 0, "tp": 0} for ty in SCENARIO_TO_INSIGHT}
    others: dict[str, int] = {}
    for seed in seeds:
        d = OUT_DIR / f"match_{seed:04d}"
        if not d.exists():
            d = generate(seed)
        res = score_match(d, params)
        for ty, r in res["types"].items():
            for k in ("scenarios", "detected", "insights", "tp"):
                total[ty][k] += r[k]
            total[ty]["delays"] += r["delays"]
        for k, n in res["others"].items():
            others[k] = others.get(k, 0) + n
    lines = [f"# Scenario detection, seeds {seeds[0]}-{seeds[-1]} ({len(seeds)} matches)", "",
             "| Scenario | Insight | Scenarios | Recall | Insights | Precision | Median delay (s) |", "|---|---|---|---|---|---|---|"]
    for ty, r in total.items():
        recall = f"{r['detected']}/{r['scenarios']} ({100 * r['detected'] / max(r['scenarios'], 1):.0f}%)"
        prec = f"{r['tp']}/{r['insights']} ({100 * r['tp'] / r['insights']:.0f}%)" if r["insights"] else "n/a"
        delay = f"{statistics.median(r['delays']):.0f}" if r["delays"] else "n/a"
        lines.append(f"| {ty} | {SCENARIO_TO_INSIGHT[ty]} | {r['scenarios']} | {recall} | {r['insights']} | {prec} | {delay} |")
    per_match = ", ".join(f"{k} {n / len(seeds):.1f}" for k, n in sorted(others.items())) or "none"
    lines += ["", f"Other insights per match: {per_match}.", "",
              f"True positive: same type and team (and player), Insight time in [start, end + {GRACE_S:.0f} s]. "
              "Recall and delay per scenario, precision per Insight."]
    return "\n".join(lines) + "\n"


def parse_seeds(spec: str) -> list[int]:
    lo, _, hi = spec.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="11-30")
    ap.add_argument("--out", default=str(RESULTS), help="markdown path, or - for stdout only")
    args = ap.parse_args()
    report = evaluate(parse_seeds(args.seeds))
    print(report)
    if args.out != "-":
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report)


if __name__ == "__main__":
    main()
