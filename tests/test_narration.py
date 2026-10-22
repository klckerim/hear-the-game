import json
import re

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


def test_rejects_turkish_percent_sign_and_jargon(ctx):
    insights, names = ctx
    i = by_type(insights, "goal")
    n = i["claim_facts"]["home_score"]
    for bad in (f"Skor {n}% oldu.", f"Skor {n} % oldu.", f"Skor %{n} oldu.", f"Skor % {n} oldu."):
        assert "percent sign in Turkish (write 'yüzde N')" in verify(bad, "tr", i, names), bad
    assert verify(f"Skor yüzde {n}.", "tr", i, names) == []
    for bad in (f"Önceden yüzde {n}'ydı.", f"Skor {n}'e çıktı.", f"Yüzde {n}’si orada."):
        assert "suffix on a number in Turkish (the voice misreads it; write 'yüzde 36' and rephrase)" in verify(bad, "tr", i, names), bad
    assert verify(f"It is {n}'s day.", "en", i, names) == []  # English is not affected
    assert verify(f"It is {n}% now.", "en", i, names) == []  # the percent sign is fine in English
    assert verify("Over the last window Northport attack.", "en", i, names)
    assert verify("Tehlike seviyesi yüksek.", "tr", i, names)
    assert "code value 'off_target' (say it in words)" in verify("The shot goes off_target.", "en", i, names)
    assert verify("Şut off_target oluyor.", "tr", i, names)


def test_every_example_passes_the_verifier_and_covers_every_kind(ctx):
    from htg.narration.examples import EXAMPLES, NAMES, example_for

    for key, ex in EXAMPLES.items():
        ins = {"type": key.split(":")[0], "claim_facts": ex["facts"]}
        for persona, max_words in (("fan", 16), ("analyst", 25)):
            for lang in ("en", "tr"):
                text = ex[persona][lang]
                assert verify(text, lang, ins, NAMES) == [], (key, persona, lang)
                assert len(text.split()) <= max_words, (key, persona, lang)
        # the fan persona says at most one number (a goal's score counts as one)
        assert len(re.findall(r"\d+(?:-\d+)?", ex["fan"]["en"])) <= 1, key
    insights, names = ctx
    assert all(example_for(i, p) for i in insights for p in ("fan", "analyst"))
    assert not set(NAMES) & set(names)  # fixture names never collide with a match


class Fake:
    name = "fake"

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

    def write(self, insight, feedback=None, persona="fan"):
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
    assert fingerprint(g, "a", "fan") != fingerprint(g, "a", "analyst")
    assert narrate_insight(g, TemplateNarrator(), names, tmp_path)["source"] == {"en": "template", "tr": "template"}


def test_ssml_escapes_and_aliases(monkeypatch):
    from htg.speech import azure

    monkeypatch.setitem(azure.ALIASES, "tr", {"Usta": "Usta"})
    out = azure.ssml("Usta & Kurt <3", "tr", "tr-TR-EmelNeural")
    assert "&amp;" in out and '&lt;<sub alias="üç">3</sub>' in out and '<sub alias="Usta">Usta</sub>' in out and 'xml:lang="tr-TR"' in out
    assert "<prosody" not in out and "<prosody" in azure.ssml("Gol!", "tr", "tr-TR-EmelNeural", goal=True)


def test_turkish_integers_are_spoken_from_words():
    from htg.speech.azure import ssml, tr_words

    assert [tr_words(n) for n in (0, 7, 10, 23, 100, 105, 342)] == ["sıfır", "yedi", "on", "yirmi üç", "yüz", "yüz beş", "üç yüz kırk iki"]
    out = ssml("Son 8 dakikada yüzde 76, önceden yüzde 23. Skor 1-2, 2,3 saniye.", "tr", "v")
    assert '<sub alias="yirmi üç">23</sub>.' in out and '<sub alias="sekiz">8</sub>' in out and '<sub alias="yetmiş altı">76</sub>' in out
    assert "1-2" in out and "2,3" in out  # scores and decimals untouched
    assert "<sub" not in ssml("Up from 23.", "en", "v")


def test_cache_hits_per_persona(ctx, tmp_path):
    insights, names = ctx
    g = by_type(insights, "goal")
    n = Fake([{"en": narrate(g, "en"), "tr": narrate(g, "tr")}] * 2)
    for persona in ("fan", "analyst", "fan", "analyst"):
        assert narrate_insight(g, n, names, tmp_path, persona)["source"]["en"] == "llm"
    assert len(n.calls) == 2  # one model call per persona, then cache hits


def test_demo_cache_covers_every_chapter_mode_and_favourite():
    """The committed seed-7 demo cache must hit for everything a demo session can speak: prompt version, model, persona."""
    from htg.narration.pregen import demo_speech
    from htg.narration.service import CACHE_DIR
    from services.engine.serve import CHAPTERS

    _, rows = demo_speech(7)
    assert {c for c, _, _ in rows} == set(CHAPTERS) and {m["persona"] for _, m, _ in rows} == {"fan", "analyst"}
    missing = [(c, m["persona"], i["type"]) for c, m, i in rows
               if not (CACHE_DIR / f"{fingerprint(i, 'foundry:gpt-5-mini', m['persona'])}.json").exists()]
    assert not missing


def test_cached_flag_and_telemetry_is_off_without_connection_string(ctx, tmp_path, monkeypatch):
    from htg import telemetry

    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    assert telemetry.setup() is False
    insights, names = ctx
    first = narrate_insight(insights[0], TemplateNarrator(), names, tmp_path)
    again = narrate_insight(insights[0], TemplateNarrator(), names, tmp_path)
    assert first["cached"] is False and again["cached"] is True and again["en"] == first["en"]
