"""Measure the narration layer.

    HTG_ENV=azure python -m eval.narration --seeds 11-30 --limit 100 --samples eval/results/narration_samples.jsonl
    python -m eval.narration --seeds 11-30 --limit 100                  # mutations only (no Azure)

Live part: Foundry narrator + Verifier + Azure voice on a sample of spoken Insights (no cache): first-pass Verifier rate,
template-fallback rate per language, model and TTS latency. Mutation part: the Verifier on template sentences with one
deliberate error. Mutations are synthetic, so the catch rate says the checks work, not how often a real model errs.
`--samples` writes one JSON row per Insight with every draft the Verifier rejected: real model errors caught in practice.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import statistics
import tempfile
import time
from pathlib import Path

from htg.env import load_env
from htg.narration.foundry import PROMPT_VERSION
from htg.narration.pregen import spoken_insights
from htg.narration.service import LANGS, get_narrator, known_names, narrate_insight
from htg.narration.templates import narrate
from htg.narration.verifier import verify

RESULTS = Path(__file__).resolve().parent / "results" / "narration.md"
# Earlier live runs (same seeds 11-30, gpt-5-mini, EN+TR in one call), kept so the before/after stays visible.
HISTORY = ["| 2026-10-21 | 1 | default | 100 | 10.73 s / 17.42 s | 100% / 100% |",
           "| 2026-10-21 | 1 | minimal | 30 | 1.87 s / 4.90 s | 93% / 93% |",
           "| 2026-10-21 | 2 | default | 100 | 7.71 s / 17.51 s | 100% / 100% |",
           "| 2026-10-21 | 2 | minimal | 100 | 1.58 s / 2.79 s | 100% / 100% |"]
NOTES = ["Reading the prompt-2 samples ([narration_samples_prompt2.jsonl](narration_samples_prompt2.jsonl)) by hand found what",
         "the Verifier then missed: 13 of 200 accepted sentences read out a code value (`off_target`), some invented shot locations",
         "(\"from the edge\"), and one goal sentence on the demo match credited the score to the wrong team.",
         "Fixes: a Verifier rule for code values, prompt 3 (say only what the facts say), and goal facts",
         "without the opponent's name, so naming the wrong team fails the name check.",
         "Invented details without a number or a name are still not caught deterministically."]
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


class Recording:
    """Wraps a narrator and keeps every draft it wrote, so rejected drafts can be reported next to the accepted text."""

    def __init__(self, narrator) -> None:
        self.inner, self.name, self.drafts = narrator, narrator.name, []

    @property
    def tokens(self) -> int:
        return getattr(self.inner, "tokens", 0)

    def write(self, insight: dict, feedback: dict | None = None) -> dict:
        draft = self.inner.write(insight, feedback)
        self.drafts.append(draft)
        return draft


def reason_kind(reason: str) -> str:
    """'number 46 is not in claim_facts' -> 'number not in claim_facts'; groups Verifier reasons for counting."""
    words = reason.split()
    if words[0] in ("number", "name") and "is not in claim_facts" in reason:
        return f"{words[0]} not in claim_facts"
    return re.sub(r" '[^']*'", "", reason).split(" (")[0]


def sample_row(ins: dict, n: dict, drafts: list[dict], names: list[str]) -> dict:
    rejected, pending = [], set(LANGS)  # like the service: a retry is only judged for the languages still open
    for k, d in enumerate(drafts, 1):
        for lang in sorted(pending):
            if bad := verify(str(d.get(lang, "")), lang, ins, names):
                rejected.append({"attempt": k, "lang": lang, "text": str(d.get(lang, "")), "reasons": bad})
            else:
                pending.discard(lang)
    return {"insight_id": ins["insight_id"], "type": ins["type"], "facts": json.dumps(ins["claim_facts"], ensure_ascii=False),
            "en": n["en"], "tr": n["tr"], "source": n["source"], "attempts": n["attempts"], "rejected": rejected}


def real_catches(rows: list[dict]) -> list[str]:
    first = [r for row in rows for r in row["rejected"] if r["attempt"] == 1]
    retries = sum(r["attempt"] > 1 for row in rows for r in row["rejected"])
    kinds: dict[str, int] = {}
    for r in first:
        for k in {reason_kind(x) for x in r["reasons"]}:
            kinds[k] = kinds.get(k, 0) + 1
    out = ["## Real catches (model errors the Verifier stopped)", "",
           "Unlike the mutation test below, these are drafts the model actually wrote on reporting seeds. A rejected sentence is never",
           "spoken: the model gets the reasons for one retry, then the template sentence is used.", "",
           f"Rejected first drafts: {len(first)} of {2 * len(rows)} sentences (EN {sum(r['lang'] == 'en' for r in first)}, "
           f"TR {sum(r['lang'] == 'tr' for r in first)}); rejected retries: {retries}.", ""]
    if kinds:
        ranked = sorted(kinds.items(), key=lambda x: -x[1])
        out += ["| reason | rejected first drafts |", "|---|---|", *[f"| {k} | {v} |" for k, v in ranked], ""]
    shown = 0
    for row in rows:
        for r in row["rejected"]:
            if r["attempt"] != 1 or row["source"][r["lang"]] != "llm" or shown >= 3:
                continue
            shown += 1
            out += [f"**Example {shown}** ({row['type']}, {r['lang'].upper()})", "",
                    f"- facts: `{row['facts']}`", f"- rejected draft: \"{r['text']}\"", f"- Verifier: {'; '.join(r['reasons'])}",
                    f"- accepted retry: \"{row[r['lang']]}\"", ""]
    return out


def live_part(items: list[tuple[dict, list[str]]], samples: Path | None) -> list[str]:
    from htg.speech.azure import AzureSpeech

    narrator, tmp = Recording(get_narrator()), tempfile.mkdtemp()
    speech = AzureSpeech(Path(tmp) / "audio")
    res, tts, lat, rows = [], [], [], []
    for ins, names in items:
        narrator.drafts = []
        n = narrate_insight(ins, narrator, names, Path(tmp) / "narr")
        res.append(n)
        rows.append(sample_row(ins, n, narrator.drafts, names))
        lat.append(n["latency_s"])
        for lang in ("en", "tr"):
            t0 = time.perf_counter()
            if speech.synthesize(n[lang], lang, ins["type"] == "goal"):
                tts.append(time.perf_counter() - t0)
    rows_md = []
    first = [pct(sum(r["first_pass"][lg] for r in res) / len(res)) for lg in ("en", "tr")]
    fall = [pct(sum(r["source"][lg] == "template" for r in res) / len(res)) for lg in ("en", "tr")]
    rows_md.append(f"| first-pass Verifier rate | {first[0]} | {first[1]} |")
    rows_md.append(f"| template fallback rate (after one retry) | {fall[0]} | {fall[1]} |")
    if samples:
        samples.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    effort = os.environ.get("FOUNDRY_REASONING_EFFORT", "").strip() or "default"
    today = datetime.date.today().isoformat()
    table = ["| | EN | TR |", "|---|---|---|", *rows_md]
    return [f"## Live model and voice ({len(res)} Insights, model `{narrator.name}`, reasoning effort `{effort}`, "
            f"prompt v{PROMPT_VERSION}, {today})", "", *table, "",
            f"- Narration latency per Insight, EN+TR in one call incl. retries (p50 / p95): {quantiles(lat)}",
            f"- TTS latency per clip (p50 / p95): {quantiles(tts)} over {len(tts)} clips",
            f"- Model tokens: {narrator.tokens}; characters sent to TTS: {speech.characters}", "",
            "### Latency before and after (all measured, same seeds and model)", "",
            "| date | prompt | reasoning effort | Insights | narration p50 / p95 | first-pass EN / TR |", "|---|---|---|---|---|---|",
            *HISTORY, f"| {today} | {PROMPT_VERSION} | {effort} | {len(res)} | {quantiles(lat)} | {first[0]} / {first[1]} |", "",
            *NOTES, "",
            *real_catches(rows)]


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


def main(seeds: list[int], limit: int, mode: str, out: Path = RESULTS, samples: Path | None = None) -> None:
    load_env()
    items = sample(seeds, limit, mode)
    azure = os.environ.get("HTG_ENV") == "azure"
    lines = ["# Narration evaluation", "",
             f"Seeds {seeds[0]}-{seeds[-1]} (reporting seeds), mode `{mode}`, {len(items)} spoken Insights sampled evenly.", ""]
    lines += live_part(items, samples) if azure else ["## Live model and voice", "", "Not run (needs `HTG_ENV=azure`).", ""]
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
    ap.add_argument("--samples", type=Path, help="write one JSON row per Insight, with every rejected draft (needs HTG_ENV=azure)")
    a = ap.parse_args()
    main(parse_seeds(a.seeds), a.limit, a.mode, a.out, a.samples)
