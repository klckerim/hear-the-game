import asyncio
import json
from pathlib import Path

import websockets
from jsonschema import Draft202012Validator

from htg.adapters.local import WebSocketBroadcaster
from htg.replay import iter_items
from services.engine.run_local import LivePipeline, apply_listener_message, warm_up

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def run(match_dir, start_minute=0):
    pipe = LivePipeline(json.loads((match_dir / "meta.json").read_text()))
    return [m for item in iter_items(match_dir, start_minute) for m in pipe.feed(item)]


def test_messages_are_valid_and_deterministic(synth_dir):
    msgs = run(synth_dir, 10)
    assert msgs == run(synth_dir, 10)
    state_v = Draft202012Validator(json.loads((SCHEMAS / "state.schema.json").read_text()))
    insight_v = Draft202012Validator(json.loads((SCHEMAS / "insight.schema.json").read_text()))
    kinds = {m["type"] for m in msgs}
    assert {"state", "event_cue", "insight", "speech"} <= kinds
    for m in msgs:
        if m["type"] == "state":
            assert len(m["packets"]) == 2
            for pk in m["packets"]:
                state_v.validate(pk)
        elif m["type"] == "insight":
            insight_v.validate(m["insight"])
        elif m["type"] == "speech":
            assert m["text"]["en"] and m["text"]["tr"] and m["evidence"] and m["team"] in ("HOME", "AWAY") and m["persona"] == "fan"


def test_every_speech_follows_its_insight_and_is_told_once(synth_dir):
    msgs = run(synth_dir)
    seen, told = set(), set()
    for m in msgs:
        if m["type"] == "insight":
            seen.add(m["insight"]["insight_id"])
        elif m["type"] == "speech":
            assert m["insight_id"] in seen and m["insight_id"] not in told
            told.add(m["insight_id"])


def test_broadcaster_waits_for_listener_and_delivers():
    async def go():
        bus = WebSocketBroadcaster(port=0)
        await bus.start()
        async with websockets.connect(f"ws://localhost:{bus.port}") as ws:
            await asyncio.wait_for(bus.wait_for_client(), 2)
            await bus.publish({"type": "hello"})
            assert json.loads(await asyncio.wait_for(ws.recv(), 2)) == {"type": "hello"}
        await bus.close()

    asyncio.run(go())


def test_broadcaster_passes_listener_messages_to_handler():
    async def go():
        got: list[dict] = []
        bus = WebSocketBroadcaster(port=0, on_message=got.append)
        await bus.start()
        async with websockets.connect(f"ws://localhost:{bus.port}") as ws:
            await ws.send("not json")
            await ws.send(json.dumps({"type": "set_mode", "mode": "analyst"}))
            await ws.send(json.dumps({"type": "hello"}))
            await asyncio.sleep(0.2)
        await bus.close()
        assert got[0] == {"type": "set_mode", "mode": "analyst"}

    asyncio.run(go())


def test_hello_lists_outfield_players_and_cues_carry_player(synth_dir):
    meta = json.loads((synth_dir / "meta.json").read_text())
    pipe = LivePipeline(meta)
    hello = pipe.hello()
    assert len(hello["teams"]["HOME"]["players"]) == 10 and all({"id", "name"} == set(p) for p in hello["teams"]["AWAY"]["players"])
    cues = [m for item in iter_items(synth_dir) for m in pipe.feed(item) if m["type"] == "event_cue"]
    assert cues and all(c["player_id"] for c in cues if c["kind"] in ("pass", "shot", "goal"))
    assert [c["period"] for c in cues if c["kind"] == "period_end"] == [1, 2]  # half-time and full-time whistles reach the client


def test_listener_messages_set_mode_persona_and_favourite(synth_dir):
    meta = json.loads((synth_dir / "meta.json").read_text())
    pipe = LivePipeline(meta)
    for msg in ({"type": "set_mode", "mode": "analyst"}, {"type": "set_favourite", "team": "AWAY"}, {"type": "set_mode", "mode": "loud"},
                {"type": "set_favourite", "team": "the Reds"}):
        apply_listener_message(pipe, msg)
    assert (pipe.mode, pipe.favourite) == ("analyst", "AWAY")
    speech = [m for item in iter_items(synth_dir) for m in pipe.feed(item) if m["type"] == "speech"]
    assert speech and all(m["persona"] == "analyst" for m in speech)
    apply_listener_message(pipe, {"type": "set_favourite", "team": None})
    assert pipe.favourite is None
    goals = sum(json.loads(line)["type"] == "goal" for line in (synth_dir / "events.jsonl").open())
    assert sum(pipe.hello()["score"].values()) == goals  # hello carries the score reached so far


def test_warm_up_matches_full_run(synth_dir):
    meta = json.loads((synth_dir / "meta.json").read_text())
    full = LivePipeline(meta)
    expected = [m for item in iter_items(synth_dir) for m in full.feed(item) if item.t >= 600.0]
    warm = LivePipeline(meta)
    warm_up(warm, synth_dir, 10)
    got = [m for item in iter_items(synth_dir, 10) for m in warm.feed(item)]
    assert got == expected
    assert any(m["type"] == "insight" for m in got)


def test_resolver_uses_service_and_falls_back_on_timeout(synth_dir, tmp_path, monkeypatch):
    import base64
    import time

    from htg.narration import service
    from services.engine.resolve import SpeechResolver, is_stale

    monkeypatch.setattr("services.engine.resolve.narrate_insight",
                        lambda i, n, names, persona: service.narrate_insight(i, n, names, tmp_path, persona))
    meta = json.loads((synth_dir / "meta.json").read_text())
    pipe = LivePipeline(meta)
    msgs = [m for item in iter_items(synth_dir) for m in pipe.feed(item)]
    ins = {m["insight"]["insight_id"]: m["insight"] for m in msgs if m["type"] == "insight"}
    sp = next(m for m in msgs if m["type"] == "speech")

    class Voice:
        def synthesize(self, text, lang, goal=False):
            return b"x" * 6000

    from htg.adapters.local import NoSpeech, TemplateNarrator
    names = service.known_names(meta)
    ok = asyncio.run(SpeechResolver(TemplateNarrator(), Voice(), names, True).resolve(sp, ins[sp["insight_id"]]))
    assert base64.b64decode(ok["audio"]["tr"]) == b"x" * 6000 and ok["duration_s"]["en"] == 1.0 and ok["text"]["en"]

    class Slow(Voice):
        def synthesize(self, text, lang, goal=False):
            time.sleep(0.5)

    slow = SpeechResolver(TemplateNarrator(), Slow(), names, True, timeout=0.05)
    late = asyncio.run(slow.resolve(sp, ins[sp["insight_id"]]))
    assert late["audio"] == {"en": None, "tr": None} and late["text"] == sp["text"]
    assert late["source"] == {"en": "template", "tr": "template"}
    local = asyncio.run(SpeechResolver(TemplateNarrator(), NoSpeech(), names, False).resolve(sp, ins[sp["insight_id"]]))
    assert local["text"] == sp["text"] and local["audio"]["en"] is None
    assert is_stale({"priority": 3, "t": 10}, 19) and not is_stale({"priority": 3, "t": 10}, 17)
    assert not is_stale({"priority": 5, "t": 10}, 99)


def test_insight_evidence_points_match_their_events_and_stay_on_the_pitch(synth_dir):
    events = {e["seq"]: e for e in map(json.loads, (synth_dir / "events.jsonl").open())}
    insights = [m for m in run(synth_dir) if m["type"] == "insight"]
    assert {m["insight"]["type"] for m in insights} >= {"goal", "chance", "pressure_shift"}
    for m in insights:
        ins, pts = m["insight"], m["evidence_points"]
        assert m["text"]["en"] and m["text"]["tr"]
        assert [p["seq"] for p in pts] == [s for s in ins["evidence"] if events[s].get("start")]
        for p in pts:
            ev = events[p["seq"]]
            pos = ev["end"] if ins["type"] == "flank_overload" else ev["start"]
            assert (p["t"], p["type"], p["team"], p["x"], p["y"]) == (ev["t"], ev["type"], ev["team"], pos["x"], pos["y"])
            assert 0 <= p["x"] <= 105 and 0 <= p["y"] <= 68
        if ins["type"] == "flank_overload":  # every counted pass ended inside the shaded band
            assert all(m["zone"]["y"][0] <= p["y"] <= m["zone"]["y"][1] for p in pts)
        assert (m["zone"] is None) == (ins["type"] != "flank_overload")


def test_evidence_points_are_capped_at_30(synth_dir):
    pipe = LivePipeline(json.loads((synth_dir / "meta.json").read_text()))
    for item in iter_items(synth_dir):
        pipe.feed(item)
    seqs = [e["seq"] for e in map(json.loads, (synth_dir / "events.jsonl").open()) if e.get("start")][:40]
    pts = pipe.evidence_points({"type": "tempo_change", "evidence": seqs})
    assert [p["seq"] for p in pts] == seqs[-30:]


def test_flank_zone_follows_the_attacking_frame():
    from htg.engine.detectors import Params
    from services.engine.run_local import evidence_zone

    p = Params()
    flank = lambda team, side: evidence_zone({"type": "flank_overload", "team": team, "claim_facts": {"side": side}}, p)["y"]  # noqa: E731
    assert flank("HOME", "left") == [p.flank_high_y, 68.0] and flank("HOME", "right") == [0.0, p.flank_low_y]
    assert flank("AWAY", "left") == [0.0, 68.0 - p.flank_high_y] and flank("AWAY", "right") == [68.0 - p.flank_low_y, 68.0]
    assert evidence_zone({"type": "pressure_shift", "team": "HOME", "claim_facts": {}}, p) is None


def test_shot_and_goal_cues_carry_where_the_shot_was_taken(synth_dir):
    events = list(map(json.loads, (synth_dir / "events.jsonl").open()))
    cues = [m for m in run(synth_dir) if m["type"] == "event_cue"]
    shots = {e["seq"]: e for e in events if e["type"] == "shot"}
    for c in cues:
        if c["kind"] == "shot":
            s = shots[c["seq"]]
            assert (c["x"], c["y"], c["speed_mps"], c["outcome"]) == (s["start"]["x"], s["start"]["y"], s["speed_mps"], s["outcome"])
        elif c["kind"] == "goal":
            scorer = [s for s in shots.values() if s["team"] == c["team"] and s["seq"] < c["seq"]][-1]
            assert scorer["outcome"] == "goal" and (c["x"], c["y"]) == (scorer["start"]["x"], scorer["start"]["y"])
        elif c["kind"] == "pass" and "length_m" in c:
            assert 0 < c["length_m"] < 130
