"""Measure the narration layer.

    HTG_ENV=azure python -m eval.narration --seeds 11-30 --limit 100    # model + TTS (a few cents), plus mutations
    python -m eval.narration --seeds 11-30 --limit 100                  # mutations only (no Azure)

Live part: Foundry narrator + Verifier + Azure voice on a sample of spoken Insights (no cache): first-pass Verifier rate,
template-fallback rate per language, model and TTS latency. Mutation part: the Verifier on template sentences with one
deliberate error. Mutations are synthetic, so the catch rate says the checks work, not how often a real model errs.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import statistics
import tempfile
import time
from pathlib import Path

from htg.env import load_env
from htg.narration.pregen import spoken_insights
from htg.narration.service import get_narrator, known_names, narrate_insight
from htg.narration.templates import narrate
from htg.narration.verifier import verify

RESULTS = Path(__file__).resolve().parent / "results" / "narration.md"
CAUSE = {"en": " because of tiredness.", "tr": " çünkü yoruldular."}
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def parse_seeds(s: str) -> list[int]:
    a, _, b = s.partition("-")
    return list(range(int(a), int(b or a) + 1))


def sample(seeds: list[int], limit: int, mode: str) -> list[tuple[dict, list[str]]]:
    """About limit/len(seeds) spoken Insights per seed, evenly spread through each match. Returns (insight, known names)."""
    per, out = max(1, -(-limit // len(seeds))), []
    for seed in seeds:
        meta, spoken = spoken_insights(seed, mode)
        names = known_names(meta)
        step = max(1, len(spoken) // per)
        out += [(ins, names) for _, ins in spoken[::step][:per]]
    return out[:limit]


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def quantiles(xs: list[float]) -> str:
    xs = sorted(xs)
    return f"{statistics.median(xs):.2f} s / {xs[min(len(xs) - 1, int(0.95 * len(xs)))]:.2f} s" if xs else "n/a"


def live_part(items: list[tuple[dict, list[str]]]) -> list[str]:
    from htg.speech.azure import AzureSpeech

    narrator, tmp = get_narrator(), tempfile.mkdtemp()
    speech = AzureSpeech(Path(tmp) / "audio")
    res, tts, lat = [], [], []
    for ins, names in items:
        n = narrate_insight(ins, narrator, names, Path(tmp) / "narr")
        res.append(n)
        lat.append(n["latency_s"])
        for lang in ("en", "tr"):
            t0 = time.perf_counter()
            if speech.synthesize(n[lang], lang):
                tts.append(time.perf_counter() - t0)
    rows = ["| | EN | TR |", "|---|---|---|"]
    first = [pct(sum(r["first_pass"][lg] for r in res) / len(res)) for lg in ("en", "tr")]
    fall = [pct(sum(r["source"][lg] == "template" for r in res) / len(res)) for lg in ("en", "tr")]
    rows.append(f"| first-pass Verifier rate | {first[0]} | {first[1]} |")
    rows.append(f"| template fallback rate (after one retry) | {fall[0]} | {fall[1]} |")
    return [f"## Live model and voice ({len(res)} Insights, model `{narrator.name}`)", "", *rows, "",
            f"- Narration latency per Insight, EN+TR in one call incl. retries (p50 / p95): {quantiles(lat)}",
            f"- TTS latency per clip (p50 / p95): {quantiles(tts)} over {len(tts)} clips",
            f"- Model tokens: {getattr(narrator, 'tokens', 0)}; characters sent to TTS: {speech.characters}", ""]


def mutate(ins: dict, names: list[str], lang: str, rng: random.Random) -> dict[str, str]:
    text, f = narrate(ins, lang), ins["claim_facts"]
    out = {"added cause": text.rstrip(".") + CAUSE[lang]}
    nums = list(NUM.finditer(text))
    if nums:
        m = rng.choice(nums)
        out["changed number"] = text[:m.start()] + str(int(float(m.group().replace(",", "."))) + 37) + text[m.end():]
    player = f.get("player")
    others = [n for n in names if n != player and n not in f.values() and n.isalpha() and n[0].isupper() and not n.startswith("the")]
    if player and player in text and others:
        out["swapped player"] = text.replace(player, rng.choice(others))
    return out


def mutation_part(items: list[tuple[dict, list[str]]]) -> list[str]:
    rng, caught, total = random.Random(0), {}, {}
    clean = sum(not verify(narrate(i, lg), lg, i, nm) for i, nm in items for lg in ("en", "tr"))
    for ins, names in items:
        for lang in ("en", "tr"):
            for kind, text in mutate(ins, names, lang, rng).items():
                total[kind] = total.get(kind, 0) + 1
                caught[kind] = caught.get(kind, 0) + bool(verify(text, lang, ins, names))
    rows = ["| mutation | sentences | caught |", "|---|---|---|"]
    rows += [f"| {k} | {total[k]} | {pct(caught[k] / total[k])} |" for k in sorted(total)]
    rows.append(f"| **all** | {sum(total.values())} | {pct(sum(caught.values()) / sum(total.values()))} |")
    return ["## Verifier mutation test (no Azure)", "",
            "Template sentences with one injected error. **The mutations are synthetic**: they show the checks fire,",
            "not how often a model errs.", "",
            *rows, "", f"Unmutated template sentences accepted: {clean} of {2 * len(items)} (must be all).", ""]


def main(seeds: list[int], limit: int, mode: str, out: Path = RESULTS) -> None:
    load_env()
    items = sample(seeds, limit, mode)
    azure = os.environ.get("HTG_ENV") == "azure"
    lines = ["# Narration evaluation", "",
             f"Seeds {seeds[0]}-{seeds[-1]} (reporting seeds), mode `{mode}`, {len(items)} spoken Insights sampled evenly.", ""]
    lines += live_part(items) if azure else ["## Live model and voice", "", "Not run (needs `HTG_ENV=azure`).", ""]
    lines += mutation_part(items)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="11-30")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--mode", default="casual")
    ap.add_argument("--out", type=Path, default=RESULTS)
    a = ap.parse_args()
    main(parse_seeds(a.seeds), a.limit, a.mode, a.out)
