"""Measure the Recap agent ("What did I miss?").

    HTG_ENV=azure python -m eval.recap --seeds 11-30 --n 20

Each run: a random reporting seed, a random moment in the second half, a random favourite club and persona; the listener missed the
last 10 minutes. Live Foundry agent, no cache, no TTS. Reports: sentences passing the Verifier (first draft and after the one
revision), template-fallback rate per language, tool calls per recap, latency. Every recap goes to `recap_samples.jsonl` for reading;
the reading notes at the end of `recap.md` are written by hand after reading (re-running this script overwrites them: copy first).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import statistics
from pathlib import Path

from eval.narration import parse_seeds
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import PERSONAS, known_names
from htg.recap.agent import LANGS, MAX_TOOL_CALLS, RECAP_VERSION, get_recap_model, write_recap
from htg.recap.tools import MatchRecord
from services.engine.recap import MISSED_MIN

RESULTS = Path(__file__).resolve().parent / "results"


def pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%" if d else "-"


def quantile(xs: list[float], q: float) -> float:
    return statistics.quantiles(xs, n=100, method="inclusive")[int(q * 100) - 1] if len(xs) > 1 else xs[0]


def main(seeds: list[int], n: int, rng_seed: int) -> None:
    load_env()
    model = get_recap_model()
    if model is None:
        raise SystemExit("needs HTG_ENV=azure and Foundry credentials")
    rng, rows, records = random.Random(rng_seed), [], {}
    for i in range(n):
        seed = rng.choice(seeds)
        if seed not in records:
            d = OUT_DIR / f"match_{seed:04d}"
            records[seed] = MatchRecord.load(d if d.exists() else generate(seed))
        rec = records[seed]
        t = round(rng.uniform(46 * 60, 90 * 60), 1)
        fav, persona = rng.choice([None, "HOME", "AWAY"]), rng.choice(PERSONAS)
        since = max(int(t // 60) - MISSED_MIN, 0)
        r = write_recap(rec, t, since, fav, persona, model, known_names(rec.meta), cache_dir=None)
        rows.append({"seed": seed, "t": t, "since_min": since, "favourite": fav, "persona": persona, **r})
        print(i + 1, seed, int(t // 60), fav, persona, r["source"], r["tools_used"], r["latency_s"])
    (RESULTS / "recap_samples.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    ok = [r for r in rows if "verifier" in r]  # runs where the agent answered (no model error)
    lines = [f"# Recap agent: {datetime.date.today().isoformat()}", "",
             f"`HTG_ENV=azure python -m eval.recap --seeds {seeds[0]}-{seeds[-1]} --n {n}` (reporting seeds only). Model "
             f"`{os.environ.get('FOUNDRY_MODEL')}` (reasoning effort `{os.environ.get('FOUNDRY_REASONING_EFFORT') or 'default'}`) as a "
             f"Foundry Agent Service prompt agent with 4 function tools, recap prompt v{RECAP_VERSION}. Random moment in the second half, "
             "random favourite club (or none) and persona; the listener missed the last 10 minutes. No cache, no TTS.", "",
             "| Measure | EN | TR |", "|---|---|---|"]
    for label, key in (("Sentences passing the Verifier, first draft", "first"), ("... after the one revision", "final")):
        cells = []
        for lang in LANGS:
            passed = sum(r["verifier"][key][lang][0] for r in ok)
            total = sum(r["verifier"][key][lang][1] for r in ok)
            cells.append(f"{pct(passed, total)} ({passed}/{total})")
        lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    fb = [pct(sum(r["source"][lang] == "template" for r in rows), len(rows)) for lang in LANGS]
    lines.append(f"| Template fallback (recap level) | {fb[0]} | {fb[1]} |")
    calls = [len(r["tools_used"]) for r in rows]
    lat = [r["latency_s"] for r in rows]
    tools = {}
    for r in rows:
        for name in r["tools_used"]:
            tools[name] = tools.get(name, 0) + 1
    revised = sum(r.get("revised", False) for r in ok)
    lines += ["", f"- Recaps: {len(rows)}; model errors: {len(rows) - len(ok)}; revisions asked: {revised}.",
              f"- Tool calls per recap: mean {statistics.mean(calls):.1f}, max {max(calls)} (limit {MAX_TOOL_CALLS}). "
              f"Tools used: {', '.join(f'{k} {v}' for k, v in sorted(tools.items(), key=lambda kv: -kv[1]))}.",
              f"- Latency (agent turns + tools + Verifier, no TTS): p50 {quantile(lat, 0.5):.2f} s / p95 {quantile(lat, 0.95):.2f} s.",
              "- A fallback language gets the deterministic template recap (score, the spell's possession and shots, the latest goal).",
              "", "All recaps: [recap_samples.jsonl](recap_samples.jsonl).", ""]
    (RESULTS / "recap.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="11-30")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--rng", type=int, default=0)
    a = ap.parse_args()
    main(parse_seeds(a.seeds), a.n, a.rng)
