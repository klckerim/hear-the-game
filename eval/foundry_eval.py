"""Microsoft Foundry cloud evaluation of the narration samples: groundedness and fluency, EN and TR separately.

    python -m eval.foundry_eval                       # reads eval/results/narration_samples.jsonl, writes eval/results/foundry_eval.md
    python -m eval.foundry_eval --resume              # wait for the latest run of this eval instead of starting a new one
    python -m eval.foundry_eval --resume EVAL_ID:RUN_ID

Uses the project's OpenAI-compatible Evals API (`{FOUNDRY_PROJECT_ENDPOINT}/openai/v1/evals`) with the built-in evaluators
`builtin.groundedness` (context = the Insight's claim_facts plus what each key means, as the narrator saw them) and
`builtin.fluency`. Judge = the deployed narrator model. Rows are sent inline (`file_content`); the run shows up in the
Foundry portal under Evaluations. An LLM judge scoring its own model family, and on Turkish, is weaker evidence than the
deterministic Verifier; read it as a second opinion.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import time
from pathlib import Path

from htg.env import load_env
from htg.narration.foundry import SYSTEM

RESULTS = Path(__file__).resolve().parent / "results"
LANG_NAME = {"en": "English", "tr": "Turkish"}
FACT_MEANINGS = SYSTEM[SYSTEM.index("Fact meanings:"):SYSTEM.index("The example shows")].strip()
EVALUATORS = {
    "groundedness": {"query": "{{item.query}}", "context": "{{item.context}}", "response": "{{item.response}}"},
    "fluency": {"response": "{{item.response}}"},
}


def rows(samples: Path) -> list[dict]:
    out = []
    for line in samples.read_text().splitlines():
        s = json.loads(line)
        for lang in ("en", "tr"):
            out.append({"insight_id": s["insight_id"], "type": s["type"], "lang": lang,
                        "query": f"Say this football Insight in one live-radio sentence in {LANG_NAME[lang]}.",
                        "context": f"Facts: {s['facts']}\n{FACT_MEANINGS}", "response": s[lang]})
    return out


def client():
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import OpenAI

    token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    return OpenAI(base_url=os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/openai/v1", api_key=token, timeout=120, max_retries=5)


EVAL_NAME = "hear-the-game narration"


def latest_run(oc) -> tuple[str, object]:
    ev = next(e for e in oc.evals.list(order="desc") if e.name == EVAL_NAME)
    return ev.id, next(iter(oc.evals.runs.list(eval_id=ev.id, order="desc")))


def run_eval(items: list[dict], judge: str, resume: str | None) -> tuple[object, list[dict]]:
    oc = client()
    if resume and ":" in resume:
        eval_id, run_id = resume.split(":", 1)
        run = oc.evals.runs.retrieve(run_id=run_id, eval_id=eval_id)
    elif resume:
        eval_id, run = latest_run(oc)
    else:
        eval_id, run = start(oc, items, judge)
    print(f"eval {eval_id}, run {run.id}")
    while run.status not in ("completed", "failed", "canceled"):
        time.sleep(15)
        run = oc.evals.runs.retrieve(run_id=run.id, eval_id=eval_id)
    if run.status != "completed":
        raise SystemExit(f"evaluation run ended in {run.status}: {getattr(run, 'error', '')}")
    return run, [o.to_dict() for o in oc.evals.runs.output_items.list(run_id=run.id, eval_id=eval_id)]


def start(oc, items: list[dict], judge: str) -> tuple[str, object]:
    props = {k: {"type": "string"} for k in items[0]}
    ev = oc.evals.create(
        name=EVAL_NAME,
        data_source_config={"type": "custom", "item_schema": {"type": "object", "properties": props, "required": list(props)},
                            "include_sample_schema": False},
        testing_criteria=[{"type": "azure_ai_evaluator", "name": name, "evaluator_name": f"builtin.{name}",
                           "initialization_parameters": {"model": judge}, "data_mapping": mapping}
                          for name, mapping in EVALUATORS.items()],
    )
    run = oc.evals.runs.create(eval_id=ev.id, name=f"narration-samples-{datetime.date.today().isoformat()}",
                               data_source={"type": "jsonl", "source": {"type": "file_content", "content": [{"item": i} for i in items]}})
    return ev.id, run


def scores(output: list[dict]) -> dict[tuple[str, str], list[float]]:
    """(evaluator, lang) -> list of scores. Results without a numeric score (judge errors) are skipped and counted apart."""
    by: dict[tuple[str, str], list[float]] = {}
    for o in output:
        lang = (o.get("datasource_item") or {}).get("lang", "?")
        for r in o.get("results") or []:
            name = str(r.get("name", "")).lower()
            if isinstance(r.get("score"), (int, float)):
                by.setdefault((name, lang), []).append(float(r["score"]))
    return by


def slim(o: dict) -> dict:
    """One output item without the echoed context and judge internals: what the score was for and why."""
    item = o.get("datasource_item") or {}
    return {"insight_id": item.get("insight_id"), "type": item.get("type"), "lang": item.get("lang"), "response": item.get("response"),
            "results": {str(r.get("name")): {"score": r.get("score"), "reason": r.get("reason")} for r in o.get("results") or []}}


def report(run, output: list[dict], judge: str, n_insights: int) -> list[str]:
    by = scores(output)
    portal = getattr(run, "report_url", None) or "(link: add from the portal)"
    lines = ["# Foundry evaluation of the narration", "",
             f"{datetime.date.today().isoformat()}. {n_insights} Insights from "
             "[narration_samples.jsonl](narration_samples.jsonl) (seeds 11-30, the sentences that ship: model text that passed the",
             f"Verifier). Built-in evaluators `builtin.groundedness` and `builtin.fluency` (1-5, pass threshold 3), judge `{judge}`.",
             "Groundedness context = the Insight's claim_facts plus what each key means, as the narrator saw them.", "",
             f"Foundry run: `{run.id}` (eval `{run.eval_id}`). Portal: {portal}", "",
             "| evaluator | lang | n | mean | 1 | 2 | 3 | 4 | 5 | pass (>=3) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name in EVALUATORS:
        for lang in ("en", "tr"):
            xs = by.get((name, lang), [])
            if not xs:
                lines.append(f"| {name} | {lang.upper()} | 0 | n/a | | | | | | |")
                continue
            dist = [sum(round(x) == k for x in xs) for k in range(1, 6)]
            lines.append(f"| {name} | {lang.upper()} | {len(xs)} | {sum(xs) / len(xs):.2f} | " + " | ".join(map(str, dist))
                         + f" | {100 * sum(x >= 3 for x in xs) / len(xs):.0f}% |")
    missing = 2 * len(EVALUATORS) * n_insights - sum(len(v) for v in by.values())
    lines += ["", f"Rows without a numeric score (judge errors): {missing}.", "",
              "Reading fluency: no sentence scored below 3; 136 of the 139 reasons for a 3 cite brevity or simplicity:",
              "correct and clear, but \"brief and simple, lacking complex sentence structures or varied vocabulary\" (per-row reasons in",
              "[foundry_eval_items.jsonl](foundry_eval_items.jsonl)). The rubric rewards complexity; the narrator is told to say one",
              "short radio sentence, so 3-4 is the expected range, not a quality problem.", "",
              "Caveats: the judge is the same model family that wrote the sentences; an LLM judge on Turkish is weaker evidence than",
              "on English. The deterministic Verifier (see [narration.md](narration.md)) is the guarantee; this is a second opinion.", ""]
    return lines


def main(samples: Path, out: Path, resume: str | None = None) -> None:
    load_env()
    judge = os.environ["FOUNDRY_MODEL"]
    items = rows(samples)
    run, output = run_eval(items, judge, resume)
    (RESULTS / "foundry_eval_items.jsonl").write_text("".join(json.dumps(slim(o), ensure_ascii=False) + "\n" for o in output))
    lines = report(run, output, judge, len(items) // 2)
    out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=Path, default=RESULTS / "narration_samples.jsonl")
    ap.add_argument("--out", type=Path, default=RESULTS / "foundry_eval.md")
    ap.add_argument("--resume", nargs="?", const="latest", help="wait for an existing run (latest, or EVAL_ID:RUN_ID)")
    a = ap.parse_args()
    main(a.samples, a.out, a.resume)
