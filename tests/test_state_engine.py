import asyncio
import json
from pathlib import Path

import jsonschema
import numpy as np
import pytest

from htg.adapters.local import FileEventSource, WebSocketBroadcaster
from htg.engine.state import StateEngine, p99_xt
from htg.replay import Item, iter_items, replay

ROOT = Path(__file__).resolve().parents[1]
STATE_SCHEMA = json.loads((ROOT / "schemas" / "state.schema.json").read_text())


def ball(t, x, y, team="HOME", in_play=True):
    return Item(t, "ball", {"t": t, "x": x, "y": y, "team": team, "in_play": in_play, "period": 1})


def pressure_event(t, team):
    return Item(t, "event", {"seq": 0, "t": t, "type": "pressure", "team": team})


def run(items, engine=None):
    engine = engine or StateEngine.from_calibration()
    return [p for item in items for p in engine.step(item)]


# --- replay ---------------------------------------------------------------------------------------------------

def test_replay_is_time_ordered_and_ball_first_on_ties(synth_dir):
    items = list(iter_items(synth_dir))
    assert [i.t for i in items] == sorted(i.t for i in items)
    for a, b in zip(items, items[1:], strict=False):
        if a.t == b.t and a.kind == "event" and b.kind == "event":
            assert a.data["seq"] < b.data["seq"]
        if a.t == b.t:
            assert ("ball", "event", "physical").index(a.kind) <= ("ball", "event", "physical").index(b.kind)


def test_replay_start_minute_and_determinism(synth_dir):
    a = list(iter_items(synth_dir, start_minute=10))
    assert a and min(i.t for i in a) >= 600
    assert a == list(iter_items(synth_dir, start_minute=10))


def test_physical_rows_are_released_after_their_minute(synth_dir):
    for i in iter_items(synth_dir):
        if i.kind == "physical":
            assert i.t == (i.data["minute"] + 1) * 60


def test_async_replay_at_infinite_speed_matches_sync(synth_dir):
    async def collect():
        return [i async for i in FileEventSource(synth_dir, speed=float("inf"), start_minute=80)]

    assert asyncio.run(collect()) == list(iter_items(synth_dir, start_minute=80))


def test_replay_rejects_bad_speed(synth_dir):
    async def go():
        async for _ in replay(synth_dir, speed=0):
            pass

    with pytest.raises(ValueError):
        asyncio.run(go())


# --- state engine ---------------------------------------------------------------------------------------------

def test_packets_match_schema(synth_dir):
    validator = jsonschema.Draft202012Validator(STATE_SCHEMA)
    packets = run(iter_items(synth_dir))
    assert len(packets) == 54000
    for p in packets[::7]:
        validator.validate(p)


def test_same_seed_gives_identical_packets(synth_dir):
    assert run(iter_items(synth_dir)) == run(iter_items(synth_dir))


def test_danger_rises_towards_goal_for_both_teams():
    e = StateEngine.from_calibration()
    home = [run([ball(0, x, 34)], e)[0]["danger"] for x in (20, 60, 90, 100)]
    assert home == sorted(home) and home[-1] > home[0]
    away = [run([ball(0, x, 34, "AWAY")], e)[0]["danger"] for x in (85, 45, 15, 5)]
    assert away == sorted(away) and away[-1] > away[0]
    assert run([ball(0, 100, 34)], e)[0]["danger"] == pytest.approx(run([ball(0, 5, 34, "AWAY")], e)[0]["danger"], abs=0.01)


def test_danger_is_zero_when_ball_is_dead_and_capped_at_one():
    e = StateEngine.from_calibration()
    assert run([ball(0, 100, 34, in_play=False)], e)[0]["danger"] == 0
    assert max(p["danger"] for p in run([ball(0, x / 2, y) for x in range(0, 211) for y in range(0, 69, 4)], e)) == 1.0


def test_danger_p99_is_close_to_one_on_a_match(synth_dir):
    engine = StateEngine.from_calibration()
    p99 = p99_xt(engine.xt, iter_items(synth_dir))
    assert p99 / engine.danger_p99 == pytest.approx(1.0, abs=0.2)


def test_pressure_is_zero_without_pressure_events(synth_dir):
    items = [i for i in iter_items(synth_dir) if not (i.kind == "event" and i.data["type"] == "pressure")]
    assert max(p["pressure"] for p in run(items)) == 0
    assert max(p["pressure"] for p in run(iter_items(synth_dir))) > 0.3


def test_pressure_counts_the_opponent_and_decays():
    e = StateEngine.from_calibration()
    run([pressure_event(10.0, "AWAY")], e)
    at = {t: run([ball(t, 50, 34, "HOME")], e)[0]["pressure"] for t in (10.0, 14.0, 18.0, 70.0)}
    assert at[10.0] > at[14.0] > at[18.0] > at[70.0]
    assert at[14.0] == pytest.approx(1 - np.exp(-0.5 / 1.5), abs=1e-3)  # one half-life later
    assert at[70.0] < 0.001
    assert run([ball(10.0, 50, 34, "AWAY")], e)[0]["pressure"] == 0  # AWAY has the ball: AWAY's own pressure does not count


def test_control_is_possession_share_over_recent_minutes():
    e = StateEngine.from_calibration()
    assert run([ball(0, 50, 34, "HOME")], e)[0]["control"] == 1.0
    for k in range(1, 10):
        last = run([ball(k / 10, 50, 34, "AWAY")], e)[0]
    assert last["control"] == pytest.approx(0.1, abs=0.01)
    far = run([ball(1000, 50, 34, "AWAY")], e)[0]  # 5-minute window has moved on
    assert far["control"] == 0.0
    assert run([ball(1000.1, 50, 34, "AWAY", in_play=False)], StateEngine.from_calibration())[0]["control"] == 0.5


def test_tempo_follows_on_ball_action_rate(synth_dir):
    e = StateEngine.from_calibration()
    for k in range(60):  # one action per second for a minute: well above the calibrated average
        e.step(Item(float(k), "event", {"seq": k, "t": float(k), "type": "pass", "team": "HOME"}))
    assert run([ball(59.9, 50, 34)], e)[0]["tempo"] == 1.0
    assert run([ball(200, 50, 34)], e)[0]["tempo"] == 0.0
    tempos = [p["tempo"] for p in run(iter_items(synth_dir))][600:]
    assert 0.3 < float(np.mean(tempos)) < 0.7  # a synthetic match sits near the calibrated average


# --- local broadcaster ----------------------------------------------------------------------------------------

def test_websocket_broadcaster_delivers_to_clients():
    import websockets

    async def go():
        b = WebSocketBroadcaster(port=0)
        await b.start()
        async with websockets.connect(f"ws://localhost:{b.port}") as c1, websockets.connect(f"ws://localhost:{b.port}") as c2:
            await asyncio.sleep(0.05)
            await b.publish({"type": "state", "n": 1})
            got = [json.loads(await asyncio.wait_for(c.recv(), 2)) for c in (c1, c2)]
        await b.close()
        return got

    assert asyncio.run(go()) == [{"type": "state", "n": 1}] * 2
