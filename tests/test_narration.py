import json

import pytest

from htg.adapters.local import TemplateNarrator
from htg.narration.service import fingerprint, known_names, narrate_insight
from htg.narration.templates import narrate
from htg.narration.verifier import verify
from htg.replay import iter_items
from services.engine.run_local import LivePipeline


@pytest.fixture(scope="module")
def ctx(synth_dir):
    meta = json.loads((synth_dir / "meta.json").read_text())
    pipe = LivePipeline(meta)
    insights = [m["insight"] for item in iter_items(synth_dir, 0) for m in pipe.feed(item) if m["type"] == "insight"]
    return insights, known_names(meta)


def by_type(insights, ty):
    return next(i for i in insights if i["type"] == ty)


def test_every_template_sentence_passes(ctx):
    insights, names = ctx
    assert {i["type"] for i in insights} >= {"goal", "chance"}
    for i in insights:
        for lang in ("en", "tr"):
            assert verify(narrate(i, lang), lang, i, names) == [], (i["type"], lang, narrate(i, lang))


def test_rejects_changed_number_extra_name_number_word_cause_and_length(ctx):
    insights, names = ctx
    g = by_type(insights, "goal")
    ok = narrate(g, "en")
    other = next(n for n in names if n not in g["claim_facts"].values() and n.isalpha() and n[0].isupper())
    assert verify(ok.replace(str(g["claim_facts"]["home_score"]), "9"), "en", g, names)
    assert verify(ok + f" {other} nearly scores too.", "en", g, names)
    assert verify("Goal, and the lead is two.", "en", g, names)
    assert verify("Goal because of a mistake.", "en", g, names)
    assert verify("Gol, çünkü savunma hata yaptı.", "tr", g, names)
    assert verify("Goal " + "again " * 30, "en", g, names)
    assert verify(narrate(g, "tr") + "'in", "tr", g, names) == []  # a suffix on a known name is not a new name


class Fake:
    name = "fake"

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

    def write(self, insight, feedback=None):
        self.calls.append(feedback)
        return self.drafts.pop(0)


def test_service_retries_then_falls_back_and_caches(ctx, tmp_path):
    insights, names = ctx
    g = by_type(insights, "goal")
    bad = {"en": "Goal! 7 goals today.", "tr": narrate(g, "tr"), "used_facts": []}
    n = Fake([bad, bad])
    out = narrate_insight(g, n, names, tmp_path)
    assert out["source"] == {"en": "template", "tr": "llm"} and out["en"] == narrate(g, "en") and out["attempts"] == 2
    assert n.calls[1] and "en" in n.calls[1]  # retry carries the Verifier reasons
    narrate_insight(g, n, names, tmp_path)
    assert len(n.calls) == 2  # cache hit, no model call


def test_service_survives_model_error_without_caching(ctx, tmp_path):
    insights, names = ctx
    g = by_type(insights, "goal")

    class Boom:
        name = "boom"

        def write(self, *a, **k):
            raise RuntimeError("down")

    out = narrate_insight(g, Boom(), names, tmp_path)
    assert out["source"] == {"en": "template", "tr": "template"} and not list(tmp_path.iterdir())
    assert fingerprint(g, "a") != fingerprint(g, "b")
    assert narrate_insight(g, TemplateNarrator(), names, tmp_path)["source"]["en"] == "llm"
