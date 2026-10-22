import json
import re
from pathlib import Path

import jsonschema
import pytest

from eval.scenarios import hits, run_match
from htg.engine.detectors import Detectors
from htg.narration.templates import narrate
from htg.replay import Item

ROOT = Path(__file__).resolve().parents[1]
INSIGHT_SCHEMA = json.loads((ROOT / "schemas" / "insight.schema.json").read_text())
META = {"match_id": "t", "teams": {
    "HOME": {"name": {"en": "Northport", "tr": "Northport"}, "players": [{"player_id": "H02", "name": "Aksoy"}]},
    "AWAY": {"name": {"en": "Valemont", "tr": "Valemont"}, "players": [{"player_id": "A02", "name": "Moreau"}]}}}


@pytest.fixture(scope="module")
def seed42(synth_dir):
    truth = json.loads((synth_dir / "truth.json").read_text())["scenarios"]
    return run_match(synth_dir), truth


def calm_stream(minutes=40):
    """Hand-built match: HOME passes every 3 s, 25% under pressure, always the same flank mix, constant physical output."""
    items, seq = [], 0
    for k in range(minutes * 20):
        t = k * 3.0
        end_y = (50.0, 34.0, 10.0, 34.0)[k % 4]
        ev = {"match_id": "t", "seq": seq, "t": t, "period": 1, "type": "pass", "team": "HOME", "player_id": "H02", "possession_id": 0,
              "start": {"x": 50.0, "y": 34.0}, "end": {"x": 60.0, "y": end_y}, "outcome": "complete", "under_pressure": k % 4 == 0}
        items.append(Item(t, "event", ev))
        seq += 1
    for m in range(minutes):
        items.append(Item((m + 1) * 60.0, "physical", {"minute": m, "team": "HOME", "player_id": "H02", "hsr_m": 8.0}))
    return sorted(items, key=lambda i: i.t)


def test_insights_validate_and_carry_evidence(seed42):
    insights, _ = seed42
    assert insights
    for i in insights:
        jsonschema.validate(i, INSIGHT_SCHEMA)
        assert i["evidence"]


def test_deterministic(synth_dir, seed42):
    assert run_match(synth_dir) == seed42[0]


def test_calm_stream_is_quiet():
    d = Detectors(META)
    assert [i for item in calm_stream() for i in d.step(item)] == []


def test_goals_match_events(synth_dir, seed42):
    goals = sum(json.loads(line)["type"] == "goal" for line in (synth_dir / "events.jsonl").open())
    assert sum(i["type"] == "goal" for i in seed42[0]) == goals


@pytest.mark.parametrize("scenario", ["press_increase", "tempo_drop", "fatigue"])
def test_detector_fires_where_scenario_exists(seed42, scenario):
    insights, truth = seed42
    scen = next(s for s in truth if s["type"] == scenario)
    assert any(hits(i, scen) for i in insights), scen


def test_pressure_shift_fires_on_pressure_jump():
    d, out, seq = Detectors(META), [], 0
    for k in range(400):  # HOME presses AWAY harder after minute 10; AWAY passes every 3 s
        t = k * 3.0
        pressed = k % 4 == 0 if t < 600 else k % 4 != 3
        ev = {"match_id": "t", "seq": seq, "t": t, "period": 1, "type": "pass", "team": "AWAY", "player_id": "A02", "possession_id": 0,
              "start": {"x": 50.0, "y": 34.0}, "end": {"x": 40.0, "y": 34.0}, "outcome": "complete", "under_pressure": pressed}
        out += d.step(Item(t, "event", ev))
        seq += 1
    shifts = [i for i in out if i["type"] == "pressure_shift"]
    assert shifts and shifts[0]["team"] == "HOME"
    assert shifts[0]["claim_facts"]["share_now_pct"] > shifts[0]["claim_facts"]["share_before_pct"]


def test_templates_use_only_claim_facts(seed42):
    insights, _ = seed42
    for i in insights:
        for lang in ("en", "tr"):
            text = narrate(i, lang)
            assert text and "{" not in text
            facts = {str(v) for v in i["claim_facts"].values()}
            for token in re.findall(r"\d+(?:[.,]\d+)?", text):  # TR writes decimals with a comma
                assert token.replace(",", ".") in facts, (lang, text)
    with pytest.raises(ValueError):
        narrate(insights[0], "de")


def test_flank_overload_fires_when_passes_shift_to_one_flank():
    d, out = Detectors(META), []
    for k in range(600):  # HOME: mixed destinations for 15 minutes, then almost every pass ends on the right flank (y < 25.5)
        t = k * 3.0
        end_y = (10.0, 34.0, 50.0, 34.0)[k % 4] if t < 900 else (10.0, 10.0, 10.0, 34.0)[k % 4]
        ev = {"match_id": "t", "seq": k, "t": t, "period": 1, "type": "pass", "team": "HOME", "player_id": "H02", "possession_id": 0,
              "start": {"x": 50.0, "y": 34.0}, "end": {"x": 60.0, "y": end_y}, "outcome": "complete"}
        out += d.step(Item(t, "event", ev))
    flank = [i for i in out if i["type"] == "flank_overload"]
    assert flank and flank[0]["claim_facts"]["side"] == "right"
