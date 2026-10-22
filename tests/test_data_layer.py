import hashlib
import json
from pathlib import Path

import jsonschema
import pandas as pd
import pytest

from htg.generate import Cal, Match, generate

ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA = json.loads((ROOT / "schemas" / "event.schema.json").read_text())


@pytest.fixture(scope="module")
def cal():
    return Cal()


@pytest.fixture(scope="module")
def match_dir(tmp_path_factory, cal):
    return generate(42, cal, tmp_path_factory.mktemp("synthetic"))


def read_events(d):
    return [json.loads(line) for line in (d / "events.jsonl").open()]


def test_every_event_matches_schema(match_dir):
    validator = jsonschema.Draft202012Validator(EVENT_SCHEMA)
    for ev in read_events(match_dir):
        validator.validate(ev)


def test_same_seed_gives_identical_match(tmp_path, cal):
    a = generate(7, cal, tmp_path / "a")
    b = generate(7, cal, tmp_path / "b")
    for name in ("events.jsonl", "truth.json", "physical.jsonl"):
        assert hashlib.sha256((a / name).read_bytes()).digest() == hashlib.sha256((b / name).read_bytes()).digest()
    pd.testing.assert_frame_equal(pd.read_parquet(a / "ball.parquet"), pd.read_parquet(b / "ball.parquet"))


def test_seed_1_events_are_pinned(tmp_path, cal):
    """README detector numbers rest on these exact matches: renaming clubs or players must not change a single event."""
    d = generate(1, cal, tmp_path)
    digest = hashlib.sha256((d / "events.jsonl").read_bytes()).hexdigest()
    # Re-pinned when fouls gained `card`; test_cards_change_no_other_field shows nothing else moved.
    assert digest == "bfafb118d6d420bdc29cb9cb3db8072b0c3bda8b2c4e2b70afef181a0f27944a"


def test_different_seeds_differ(cal):
    a, b = Match(1, cal).run(), Match(2, cal).run()
    assert [e["t"] for e in a.events[:50]] != [e["t"] for e in b.events[:50]]


def test_events_are_ordered_and_sequenced(match_dir):
    ev = read_events(match_dir)
    assert [e["seq"] for e in ev] == list(range(len(ev)))
    on_ball = [e["t"] for e in ev if e["type"] in ("pass", "carry", "shot")]
    assert on_ball == sorted(on_ball)


def test_ball_track_is_10hz_and_on_the_pitch(match_dir):
    ball = pd.read_parquet(match_dir / "ball.parquet")
    assert len(ball) == 5400 * 10
    assert ball["x"].between(0, 105).all() and ball["y"].between(0, 68).all()
    assert 0.55 < ball["in_play"].mean() < 0.75  # real football: ~55-65 minutes of 90 in play


def test_match_level_counts_are_football_like(match_dir):
    ev = pd.DataFrame(read_events(match_dir))
    counts = ev["type"].value_counts()
    assert 600 < counts["pass"] < 1300
    assert 10 < counts["shot"] < 50
    assert counts.get("goal", 0) < 10


def test_truth_is_complete_and_not_leaked(match_dir):
    truth = json.loads((match_dir / "truth.json").read_text())["scenarios"]
    assert {s["type"] for s in truth} == {"press_increase", "flank_overload", "tempo_drop", "fatigue"}
    for s in truth:
        assert 0 <= s["start"] < s["end"] <= 5400
    raw = (match_dir / "events.jsonl").read_text()
    assert "scenario" not in raw and "fatigue" not in raw


def test_fatigued_player_slows_down(match_dir):
    truth = json.loads((match_dir / "truth.json").read_text())["scenarios"]
    s = next(x for x in truth if x["type"] == "fatigue")
    phys = pd.DataFrame([json.loads(line) for line in (match_dir / "physical.jsonl").open()])
    p = phys[phys["player_id"] == s["player_id"]]
    before = p[p["minute"] * 60 < s["start"]]["hsr_m"].mean()
    after = p[p["minute"] * 60 >= s["start"] + 300]["hsr_m"].mean()
    assert after < 0.7 * before


# Hash of every event without `card`, taken before cards were added: cards come from their own RNG stream and must change nothing else.
PRE_CARD_HASHES = {1: "a8f104c7db5ee9a9", 2: "0e32a1faf1132f19", 3: "e6e714d29f8df604", 7: "0dad5431b8d730af"}


@pytest.mark.parametrize("seed", sorted(PRE_CARD_HASHES))
def test_cards_change_no_other_field(cal, seed):
    ev = Match(seed, cal).run().events
    rest = [{k: v for k, v in e.items() if k != "card"} for e in ev]
    assert hashlib.sha256(json.dumps(rest, sort_keys=True).encode()).hexdigest()[:16] == PRE_CARD_HASHES[seed]
    cards = [e["card"] for e in ev if e.get("card")]
    assert all(e["type"] == "foul" for e in ev if e.get("card"))
    assert 1 <= cards.count("yellow") <= 6
