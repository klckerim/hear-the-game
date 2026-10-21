"""Insight -> verified EN + TR narration: cache, model, Verifier, one retry, template fallback."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from htg.adapters.base import Narrator
from htg.narration.foundry import PROMPT_VERSION
from htg.narration.templates import narrate
from htg.narration.verifier import verify

LANGS = ("en", "tr")
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "narration"


def known_names(meta: dict) -> list[str]:
    """All team and player names (EN, TR) of a match; the Verifier rejects any that is not in the Insight's claim_facts."""
    names: list[str] = []
    for t in meta["teams"].values():
        names += list(t["name"].values()) + [p["name"] for p in t["players"]]
    return names


def fingerprint(insight: dict, model: str) -> str:
    key = [insight["type"], insight["team"], insight.get("player_id"), sorted(insight["claim_facts"].items()), PROMPT_VERSION, model]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, default=str).encode()).hexdigest()[:32]


def get_narrator() -> Narrator:
    if os.environ.get("HTG_ENV", "local") == "azure":
        from htg.narration.foundry import FoundryNarrator

        return FoundryNarrator()
    from htg.adapters.local import TemplateNarrator

    return TemplateNarrator()


def narrate_insight(insight: dict, narrator: Narrator, names: list[str], cache_dir: Path = CACHE_DIR) -> dict:
    """Returns {"en", "tr", "source": {lang: "llm"|"template"}, "attempts", "reasons", "latency_s"}. Never raises."""
    path = cache_dir / f"{fingerprint(insight, narrator.name)}.json"
    if path.exists():
        return json.loads(path.read_text())
    t0 = time.perf_counter()
    text: dict[str, str] = {}
    reasons: dict[str, list[str]] = {}
    attempts, errored, feedback, first_pass = 0, False, None, {}
    for _ in range(2):
        attempts += 1
        try:
            draft = narrator.write(insight, feedback)
        except Exception as e:  # model or network failure: sound and templates carry on
            errored, reasons["error"] = True, [f"{type(e).__name__}: {e}"[:200]]
            break
        feedback = {}
        if attempts == 1:
            first_pass = {lang: not verify(str(draft.get(lang, "")), lang, insight, names) for lang in LANGS}
        for lang in LANGS:
            if lang in text:
                continue
            bad = verify(str(draft.get(lang, "")), lang, insight, names)
            if bad:
                reasons[lang], feedback[lang] = bad, bad
            else:
                text[lang] = draft[lang]
                reasons.pop(lang, None)
        if len(text) == len(LANGS):
            break
    source = {lang: "llm" if lang in text and narrator.name != "template" else "template" for lang in LANGS}
    for lang in LANGS:
        text.setdefault(lang, narrate(insight, lang))
    result = {"en": text["en"], "tr": text["tr"], "source": source, "attempts": attempts, "first_pass": first_pass,
              "reasons": reasons,
              "latency_s": round(time.perf_counter() - t0, 3)}
    if not errored:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False))
    return result
