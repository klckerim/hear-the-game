import asyncio
import json

import pytest

from htg.commentary.commentator import cache_path, commentate, load_cached, verify_line
from htg.commentary.segments import Segment, Segmenter
from htg.narration.service import known_names
from htg.replay import iter_items
from services.engine import commentary
from services.engine.commentary import CommentaryStream


def segments_of(match_dir) -> list[Segment]:
    meta = json.loads((match_dir / "meta.json").read_text())
    sg, score, out = Segmenter(meta), {"HOME": 0, "AWAY": 0}, []
    for item in iter_items(match_dir):
        if item.kind == "event":
            score[item.data["team"]] += item.data["type"] == "goal"
            out += sg.step(item.data, score)
    return out


def test_segmenting_is_deterministic_and_ends_at_dead_balls(synth_dir):
    a, b = segments_of(synth_dir), segments_of(synth_dir)
    assert [(s.segment_id, s.t1, s.facts) for s in a] == [(s.segment_id, s.t1, s.facts) for s in b]
    assert all(s.t1 - s.t0 < 10.0 or s.facts["ended_by"] != "play_on" for s in a)  # play-on segments stop at 10 s
    goals = [s for s in a if s.goal]
    assert goals and all(g.facts["scorer"] and g.facts["shot_outcome"] == "goal" for g in goals)  # shot + goal are one segment
    assert len({s.segment_id for s in a}) == len(a)


class Fake:
    name = "fake"

    def __init__(self, lines: list[dict], wait_s: float = 0.0):
        self.lines, self.wait_s, self.calls = lines, wait_s, 0

    def write(self, facts: dict, recent: list[str]) -> dict:
        import time

        self.calls += 1
        time.sleep(self.wait_s)
        return {"lines": self.lines}


SEG = Segment("1-10", 100.0, 104.0, False, {"home_team": "Northport", "away_team": "Valemont", "team_in_possession": "Northport",
                                             "player_1": "Okafor", "ended_by": "shot", "shooter": "Okafor", "shot_outcome": "saved",
                                             "shot_speed_kmh": 92, "seconds_available": 10.0})
NAMES = ["Northport", "Valemont", "Okafor", "Silva"]


def test_a_line_with_an_unknown_name_or_invented_detail_is_dropped():
    fake = Fake([{"en": "Okafor... shot, 92 km/h, saved!", "tr": "Okafor vurdu, kaleci kurtardı!", "style": "excited", "offset_s": 0.5},
                 {"en": "Silva was unmarked there.", "tr": "Silva boştaydı.", "style": "calm", "offset_s": 9},
                 {"en": "A header from Okafor!", "tr": "Okafor kafayla vurdu!", "style": "excited", "offset_s": 0}])
    out = commentate(SEG, fake, NAMES, [])
    assert out["lines"] == [{"style": "excited", "offset_s": 0.5, "en": "Okafor... shot, 92 km/h, saved!",
                             "tr": "Okafor vurdu, kaleci kurtardı!"}]
    assert out["dropped"] == 1  # Silva is not in the facts; the third line is past MAX_LINES
    assert verify_line("A header from Okafor!", "en", SEG.facts, NAMES, 20)
    assert not verify_line("Valemont lead at the end of the first half.", "en", SEG.facts, NAMES, 20)  # football "half" is fine
    assert verify_line("Okafor's shot at 93 km/h", "en", SEG.facts, NAMES, 20)  # a number not in the facts


def test_goal_effect_comes_from_the_score_and_seed_7s_equaliser_is_one():
    from htg.commentary.segments import goal_effect
    from htg.generate import OUT_DIR, generate

    assert [goal_effect(1, 0), goal_effect(2, 0), goal_effect(1, 1), goal_effect(1, 2), goal_effect(3, 2)] == [
        "takes_lead", "extends_lead", "equaliser", "pulls_one_back", "takes_lead"]
    match_dir = OUT_DIR / "match_0007"
    goals = [s.facts for s in segments_of(match_dir if match_dir.exists() else generate(7)) if s.goal]
    assert [(g["scoring_team"], g["home_score"], g["away_score"], g["goal_effect"]) for g in goals] == [
        ("Valemont", 0, 1, "takes_lead"), ("Northport", 1, 1, "equaliser"), ("Valemont", 1, 2, "takes_lead")]


def test_a_lead_or_level_word_must_match_the_score():
    eq = {**SEG.facts, "ended_by": "goal", "scorer": "Okafor", "scoring_team": "Valemont", "home_score": 1, "away_score": 1,
          "goal_effect": "equaliser"}
    ahead = {**eq, "home_score": 0, "away_score": 1, "goal_effect": "takes_lead"}
    back = {**eq, "home_score": 2, "away_score": 1, "goal_effect": "pulls_one_back"}
    ok = lambda text, lang, facts: not verify_line(text, lang, facts, NAMES, 20)  # noqa: E731
    assert not ok("Goal! Okafor smashes it in, Valemont lead!", "en", eq)  # the seed-7 line, on an equaliser
    assert not ok("Gol! Okafor vurdu, Valemont öne geçti!", "tr", eq)
    assert ok("Goal! Okafor levels it, 1-1!", "en", eq) and ok("Gol! Okafor eşitledi!", "tr", eq)
    assert ok("Goal! Okafor puts Valemont ahead!", "en", ahead) and ok("Gol! Valemont öne geçti!", "tr", ahead)
    assert not ok("Goal! Okafor, and it's all square!", "en", ahead)
    assert not ok("Goal! Valemont in front again!", "en", back) and ok("Goal! Okafor pulls one back!", "en", back)
    assert not ok("Goal! Valemont's lead restored!", "en", ahead)  # history no fact carries
    assert not ok("Okafor fires in from the edge of the area!", "en", ahead)  # a place no fact carries
    assert not ok("Okafor vurdu, Valemont eşitliği sağladı!", "tr", ahead) and ok("Okafor vurdu, Valemont eşitliği sağladı!", "tr", eq)
    assert not ok("Valemont still lead as Okafor shoots.", "en", {**SEG.facts, "home_score": 1, "away_score": 1})
    assert ok("Valemont lead as Okafor shoots.", "en", {**SEG.facts, "home_score": 0, "away_score": 1})


def test_warm_up_call_is_discarded_and_never_raises():
    from htg.commentary.commentator import warm

    fake = Fake([LINE])
    assert warm(fake) is not None and fake.calls == 1

    class Broken(Fake):
        def write(self, facts: dict, recent: list[str]) -> dict:
            raise RuntimeError("no model")

    assert warm(Broken([])) is None


def test_cache_key_depends_on_match_segment_and_model(tmp_path):
    p = cache_path(7, "1-10", "fake", tmp_path)
    assert p == cache_path(7, "1-10", "fake", tmp_path)
    assert len({p, cache_path(7, "1-11", "fake", tmp_path), cache_path(8, "1-10", "fake", tmp_path),
                cache_path(7, "1-10", "other", tmp_path)}) == 4


def test_segment_ids_do_not_depend_on_where_the_session_started(synth_dir):
    """A session warmed up to minute 30 cuts the same segments from there on as a run from kick-off, so the cache key can drop the start."""
    from services.engine.run_local import LivePipeline, warm_up

    meta = json.loads((synth_dir / "meta.json").read_text())

    def run(start_minute: float) -> list[tuple]:
        pipe = LivePipeline(meta)
        warm_up(pipe, synth_dir, start_minute)
        return [(m["segment"].segment_id, m["segment"].t1, m["segment"].facts)
                for item in iter_items(synth_dir, start_minute) for m in pipe.feed(item) if m["type"] == "segment"]

    late = run(30.0)
    assert late and late == [s for s in run(0.0) if s[1] >= 30 * 60]


LINE = {"en": "Okafor... saved!", "tr": "Okafor... kurtardı!", "style": "excited", "offset_s": 0.0}


def run_stream(fake: Fake, clock_t: float, delay_s: float = 20.0) -> tuple[list[dict], CommentaryStream]:
    sent: list[dict] = []

    async def go() -> CommentaryStream:
        async def send(m: dict) -> None:
            sent.append(m)

        s = CommentaryStream(fake, None, NAMES, 7, delay_s, 1.0, "en", send, lambda: clock_t)
        s.push(SEG)
        s.close()
        await s.run()
        return s

    commentary._shared.clear()
    return sent, asyncio.run(go())


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("htg.commentary.commentator.CACHE_DIR", tmp_path)
    monkeypatch.setattr(commentary, "cache_path", lambda *a: cache_path(*a, cache_dir=tmp_path))
    return tmp_path


def test_a_live_line_is_sent_at_its_match_time_and_cached(cache_dir):
    sent, s = run_stream(Fake([LINE]), clock_t=SEG.t1 + 1)
    assert [(m["t"], m["source"], m["text"]["en"]) for m in sent] == [(104.0, "live", "Okafor... saved!")]
    assert s.counts.live == 1 and s.recent == ["Okafor... saved!"]
    assert load_cached(cache_path(7, "1-10", "fake", cache_dir))


def test_a_late_line_is_dropped_and_a_cached_one_falls_back(cache_dir):
    sent, s = run_stream(Fake([LINE]), clock_t=SEG.t1 + 18)  # 2 s before play time: inside the 3 s margin
    assert sent == [] and s.counts.silent == 1  # no budget, nothing cached yet
    run_stream(Fake([LINE]), clock_t=SEG.t1)  # an earlier session caches the segment
    slow = Fake([{**LINE, "en": "Too late"}], wait_s=0.5)
    sent, s = run_stream(slow, clock_t=SEG.t1 + 16.6)  # 0.4 s budget, the model takes 0.5 s
    assert [(m["source"], m["text"]["en"]) for m in sent] == [("fallback", "Okafor... saved!")] and s.counts.fallback == 1


def test_a_backlog_skips_to_the_newest_segment(cache_dir):
    sent: list[dict] = []

    async def go() -> CommentaryStream:
        async def send(m: dict) -> None:
            sent.append(m)

        s = CommentaryStream(Fake([LINE]), None, NAMES, 7, 20.0, 1.0, "en", send, lambda: 100.0)
        for i in range(3):
            s.push(Segment(f"1-{i}", 90.0 + i, 95.0 + i, False, SEG.facts))
        s.close()
        await s.run()
        return s

    commentary._shared.clear()
    s = asyncio.run(go())
    assert s.counts.skipped == 2 and [m["segment"] for m in sent] == ["1-2"]


def test_the_first_seconds_come_at_once_with_a_lead(synth_dir):
    import time

    from htg.replay import replay

    async def go() -> tuple[float, float]:
        t0, last = time.monotonic(), None
        async for item in replay(synth_dir, 1.0, 5.0, lead_s=3.0):
            last = item.t
            if item.t >= 5 * 60 + 3:
                break
        return time.monotonic() - t0, last

    took, _ = asyncio.run(go())
    assert took < 0.5  # 3 s of match time, no pacing


def test_serve_parses_delay_and_lang():
    from services.engine.serve import delay_of, lang_of

    assert delay_of("/ws?match=x&delay=20") == 20.0 and delay_of("/ws?delay=99") == 30.0 and delay_of("/ws?delay=x") == 0.0
    assert delay_of("/ws") == 0.0 and lang_of("/ws?lang=tr") == "tr" and lang_of("/ws?lang=de") == "en"


def test_known_names_cover_the_segment_facts(synth_dir):
    meta = json.loads((synth_dir / "meta.json").read_text())
    names = set(known_names(meta))
    for s in segments_of(synth_dir)[:50]:
        assert {v for k, v in s.facts.items() if k.startswith("player_")} <= names
