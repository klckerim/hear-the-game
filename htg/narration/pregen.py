"""Pre-generate verified narration (and audio with HTG_ENV=azure) for every spoken Insight of a demo match.

    HTG_ENV=azure python -m htg.narration.pregen --seed 3
    python -m htg.narration.pregen --find-demo        # seeds 1-10: which has a goal + 3 non-chance Insights in one 10-minute window
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from htg.adapters.local import NoSpeech
from htg.engine.director import SILENCE_S
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import get_narrator, known_names, narrate_insight
from htg.replay import iter_items
from services.engine.run_local import LivePipeline


def spoken_insights(seed: int, mode: str) -> tuple[dict, list[tuple[float, dict]]]:
    """Run the live pipeline unpaced; returns meta and (match time, Insight) for every `speech` decision."""
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    meta = json.loads((Path(match_dir) / "meta.json").read_text())
    pipe, insights, spoken = LivePipeline(meta, mode), {}, []
    for item in iter_items(match_dir):
        for m in pipe.feed(item):
            if m["type"] == "insight":
                insights[m["insight"]["insight_id"]] = m["insight"]
            elif m["type"] == "speech":
                spoken.append((m["t"], insights[m["insight_id"]]))
    return meta, spoken


def find_demo(mode: str) -> None:
    for seed in range(1, 11):
        _, spoken = spoken_insights(seed, mode)
        best = max(((sum(i["type"] == "goal" for t, i in spoken if w <= t < w + 600),
                     sum(i["type"] not in ("goal", "chance") for t, i in spoken if w <= t < w + 600), w) for w in range(0, 5400 - 600, 60)),
                   key=lambda x: (x[0] >= 1 and x[1] >= 3, x[1]))
        print(f"seed {seed}: {len(spoken)} spoken, best 10-min window from minute {best[2] // 60}: "
              f"{best[0]} goal, {best[1]} other non-chance")


def main(seed: int, mode: str) -> None:
    load_env()
    meta, spoken = spoken_insights(seed, mode)
    names, narrator = known_names(meta), get_narrator()
    speech = NoSpeech()
    if os.environ.get("HTG_ENV") == "azure":
        from htg.speech.azure import AzureSpeech

        speech = AzureSpeech()
    sources, clips, chars = Counter(), 0, 0
    for _, ins in spoken:
        n = narrate_insight(ins, narrator, names)
        for lang in ("en", "tr"):
            sources[f"{lang}:{n['source'][lang]}"] += 1
            chars += len(n[lang])
            clips += speech.synthesize(n[lang], lang, ins["type"] == "goal") is not None
    print(f"seed {seed}, mode {mode}: {len(spoken)} spoken Insights, {clips} audio clips")
    print("sources:", dict(sorted(sources.items())))
    print(f"characters narrated: {chars}; sent to TTS this run: {getattr(speech, 'characters', 0)}; "
          f"model tokens this run: {getattr(narrator, 'tokens', 0)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--mode", choices=sorted(SILENCE_S), default="casual")
    ap.add_argument("--find-demo", action="store_true")
    a = ap.parse_args()
    find_demo(a.mode) if a.find_demo else main(a.seed or 1, a.mode)
