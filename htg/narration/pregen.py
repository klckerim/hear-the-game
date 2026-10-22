"""Pre-generate verified narration (and audio with HTG_ENV=azure) for every Insight the demo can speak.

    HTG_ENV=azure python -m htg.narration.pregen --seed 7      # every chapter x mode x favourite club, then prune stale files
    python -m htg.narration.pregen --find-demo     # seeds 1-10: which has a goal + 3 non-chance Insights in one 10-minute window

A demo session starts at a chapter (warmed up like the server does), runs 15 match-minutes, and the listener may pick any mode and
favourite club; the Director can then speak a slightly different set of Insights. All of them are narrated in the persona of the mode.
The sentences go to `eval/results/demo_sentences.md` for reading before listening.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path

from htg.adapters.local import NoSpeech
from htg.engine.director import SILENCE_S
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import CACHE_DIR, fingerprint, get_narrator, known_names, narrate_insight
from htg.replay import iter_items
from services.engine.run_local import LivePipeline, warm_up
from services.engine.serve import CHAPTERS, END_AFTER_S

SENTENCES = Path(__file__).resolve().parents[2] / "eval" / "results" / "demo_sentences.md"
FAVOURITES = (None, "HOME", "AWAY")


def match(seed: int) -> tuple[dict, Path]:
    match_dir = OUT_DIR / f"match_{seed:04d}"
    if not match_dir.exists():
        match_dir = generate(seed)
    return json.loads((Path(match_dir) / "meta.json").read_text()), Path(match_dir)


def spoken_insights(seed: int, mode: str) -> tuple[dict, list[tuple[float, dict]]]:
    """Run the live pipeline unpaced over the whole match; returns meta and (match time, Insight) for every `speech` decision."""
    meta, match_dir = match(seed)
    pipe, insights, spoken = LivePipeline(meta, mode), {}, []
    for item in iter_items(match_dir):
        for m in pipe.feed(item):
            if m["type"] == "insight":
                insights[m["insight"]["insight_id"]] = m["insight"]
            elif m["type"] == "speech":
                spoken.append((m["t"], insights[m["insight_id"]]))
    return meta, spoken


def chapter_speech(warm: LivePipeline, match_dir: Path, start_minute: float, mode: str, favourite: str | None) -> list[tuple[dict, dict]]:
    """What one demo session speaks: (speech message, Insight) for a warmed copy, a mode and a favourite club, as `serve` runs it."""
    pipe = copy.deepcopy(warm)
    pipe.mode, pipe.favourite = mode, favourite
    insights, out = {}, []
    for item in iter_items(match_dir, start_minute):
        if item.t - start_minute * 60.0 > END_AFTER_S:
            break
        for m in pipe.feed(item):
            if m["type"] == "insight":
                insights[m["insight"]["insight_id"]] = m["insight"]
            elif m["type"] == "speech":
                out.append((m, insights[m["insight_id"]]))
    return out


def demo_speech(seed: int) -> tuple[dict, list[tuple[str, dict, dict]]]:
    """Every distinct (chapter, persona, Insight) a demo session can speak, in chapter and time order."""
    meta, match_dir = match(seed)
    rows: dict[tuple, tuple[str, dict, dict]] = {}
    for chapter, minute in CHAPTERS.items():
        warm = LivePipeline(meta, "casual")
        warm_up(warm, match_dir, minute)
        for mode in sorted(SILENCE_S):
            for fav in FAVOURITES:
                for msg, ins in chapter_speech(warm, match_dir, minute, mode, fav):
                    rows.setdefault((chapter, msg["persona"], ins["insight_id"]), (chapter, msg, ins))
    order = {c: k for k, c in enumerate(CHAPTERS)}
    return meta, sorted(rows.values(), key=lambda r: (order[r[0]], r[1]["persona"], r[1]["t"]))


def find_demo(mode: str) -> None:
    for seed in range(1, 11):
        _, spoken = spoken_insights(seed, mode)
        best = max(((sum(i["type"] == "goal" for t, i in spoken if w <= t < w + 600),
                     sum(i["type"] not in ("goal", "chance") for t, i in spoken if w <= t < w + 600), w) for w in range(0, 5400 - 600, 60)),
                   key=lambda x: (x[0] >= 1 and x[1] >= 3, x[1]))
        print(f"seed {seed}: {len(spoken)} spoken, best 10-min window from minute {best[2] // 60}: "
              f"{best[0]} goal, {best[1]} other non-chance")


def prune(directory: Path, keep: set[str], pattern: str) -> int:
    stale = [p for p in directory.glob(pattern) if p.name not in keep]
    for p in stale:
        p.unlink()
    return len(stale)


def main(seed: int) -> None:
    load_env()
    meta, rows = demo_speech(seed)
    names, narrator = known_names(meta), get_narrator()
    speech = NoSpeech()
    if os.environ.get("HTG_ENV") == "azure":
        from htg.speech.azure import CACHE_DIR as AUDIO_DIR
        from htg.speech.azure import AzureSpeech, clip_name

        speech = AzureSpeech()
    sources, clips, keep_text, keep_audio = Counter(), 0, set(), set()
    lines = [f"# Demo sentences (seed {seed})", "",
             "Every sentence a demo session can speak: each chapter runs 15 match-minutes from its start, in every mode and with every",
             "favourite club. Casual and Audio only use the fan persona, Analyst the analyst persona. Source `llm` = model text that",
             "passed the Verifier, `template` = fallback.", "",
             "| chapter | minute | persona | type | EN | TR | source |", "|---|---|---|---|---|---|---|"]
    for chapter, msg, ins in rows:
        persona = msg["persona"]
        n = narrate_insight(ins, narrator, names, persona=persona)
        keep_text.add(f"{fingerprint(ins, narrator.name, persona)}.json")
        for lang in ("en", "tr"):
            sources[f"{persona}:{lang}:{n['source'][lang]}"] += 1
            goal = ins["type"] == "goal"
            if speech.synthesize(n[lang], lang, goal) is not None:
                clips += 1
                keep_audio.add(clip_name(n[lang], speech.voices[lang], goal))
        t = msg["t"]
        src = "/".join(sorted(set(n["source"].values())))
        lines.append(f"| {chapter} | {int(t // 60)}:{int(t % 60):02d} | {persona} | {ins['type']} | {n['en']} | {n['tr']} | {src} |")
    SENTENCES.write_text("\n".join(lines) + "\n")
    print(f"seed {seed}: {len(rows)} (chapter, persona, Insight) rows, {len(keep_text)} narrations, {clips} audio clips")
    print("sources:", dict(sorted(sources.items())))
    print(f"model tokens this run: {getattr(narrator, 'tokens', 0)}; characters sent to TTS: {getattr(speech, 'characters', 0)}")
    if narrator.name != "template":
        print(f"pruned stale narration files: {prune(CACHE_DIR, keep_text, '*.json')}")
    if keep_audio:
        removed = prune(AUDIO_DIR, keep_audio, "*.mp3")
        size = sum(p.stat().st_size for p in AUDIO_DIR.glob("*.mp3"))
        print(f"pruned stale clips: {removed}; audio cache now {len(keep_audio)} clips, {size / 1e6:.1f} MB")
    print(f"sentences written to {SENTENCES}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mode", choices=sorted(SILENCE_S), default="casual", help="for --find-demo")
    ap.add_argument("--find-demo", action="store_true")
    a = ap.parse_args()
    find_demo(a.mode) if a.find_demo else main(a.seed)
