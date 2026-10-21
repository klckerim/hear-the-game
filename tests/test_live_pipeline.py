import asyncio
import json
from pathlib import Path

import websockets
from jsonschema import Draft202012Validator

from htg.adapters.local import WebSocketBroadcaster
from htg.replay import iter_items
from services.engine.run_local import LivePipeline

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
            assert m["text"]["en"] and m["text"]["tr"] and m["evidence"]


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
