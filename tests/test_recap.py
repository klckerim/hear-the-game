import asyncio
import json

import pytest
import websockets

from htg.narration.service import known_names
from htg.recap.agent import MAX_TOOL_CALLS, template_recap, verify_recap, write_recap
from htg.recap.tools import MatchRecord, get_insights, get_player, get_score, get_stats


@pytest.fixture(scope="module")
def rec(synth_dir):
    return MatchRecord.load(synth_dir)


@pytest.fixture(scope="module")
def names(rec):
    return known_names(rec.meta)


def first_goal_t(rec):
    return next(e["t"] for e in rec.events if e["type"] == "goal")


def test_tools_never_see_past_t(rec):
    t = first_goal_t(rec) - 1.0
    sc = get_score(rec, t)
    assert (sc["home_score"], sc["away_score"]) == (0, 0) and sc["goals"] == []
    assert get_score(rec, first_goal_t(rec))["goals"]  # the goal counts from its own moment on
    st = get_stats(rec, t, 0, 999)  # a window asked past t is clamped to t
    assert st["to_minute"] == int(t // 60)
    assert get_stats(rec, t, 0, int(t // 60)) == st  # "to the current minute" means now
    assert all(i["minute"] <= t // 60 for i in get_insights(rec, t, 0, 999)["insights"])
    pid = next(p for p in rec.players() if not p.startswith("H01"))
    later = [e for e in rec.events if e.get("player_id") == pid and e["t"] > t and e["type"] in ("pass", "carry", "shot")]
    assert get_player(rec, t, pid)["touches"] + len(later) == get_player(rec, 1e9, pid)["touches"]


def test_tools_are_deterministic(rec, synth_dir):
    again = MatchRecord.load(synth_dir)
    t = 60 * 60.0
    for f, args in ((get_score, ()), (get_stats, (50, None)), (get_insights, (30, None))):
        assert json.dumps(f(rec, t, *args)) == json.dumps(f(again, t, *args))


def test_template_recap_passes_the_verifier(rec, names):
    for t, since in ((first_goal_t(rec) + 60, 0), (60 * 60.0, 50), (rec.events[-1]["t"], 0)):
        text, facts = template_recap(rec, t, since)
        for lang in ("en", "tr"):
            kept, reasons = verify_recap(text[lang], lang, facts, names)
            assert reasons == [] and len(kept) == len(text[lang]) >= 2, (lang, text[lang], reasons)


class FakeModel:
    """Scripted agent: a list of turns, each either tool calls [(name, args)] or the final JSON text."""

    name = "fake"

    def __init__(self, turns):
        self.turns, self.inputs = list(turns), []

    def respond(self, input, previous_id):  # noqa: A002 - mirrors the Responses API
        self.inputs.append(input)
        turn = self.turns.pop(0) if self.turns else self.turns_default
        if isinstance(turn, str):
            return f"r{len(self.inputs)}", [], turn
        return f"r{len(self.inputs)}", [{"name": n, "arguments": json.dumps(a), "call_id": f"c{i}"} for i, (n, a) in enumerate(turn)], ""

    turns_default = [("get_score", {})]


def answer(en, tr):
    return json.dumps({"en": en, "tr": tr, "tools_used": []})


def test_tool_loop_stops_at_the_limit_and_falls_back(rec, names):
    model = FakeModel([])  # asks for get_score forever
    out = write_recap(rec, 60 * 60.0, 50, None, "fan", model, names, cache_dir=None)
    assert len(out["tools_used"]) == MAX_TOOL_CALLS
    assert out["source"] == {"en": "template", "tr": "template"}
    assert out["en"] == template_recap(rec, 60 * 60.0, 50)[0]["en"]


def test_a_number_not_in_the_tool_results_is_dropped(rec, names):
    sc = get_score(rec, 60 * 60.0)
    h, a = sc["home_score"], sc["away_score"]
    home = sc["home"]["team_en"]
    good_en, good_tr = f"It is {home} {h}, {sc['away']['team_en']} {a}.", f"Skor {home} {h}, {sc['away']['team_tr']} {a}."
    bad_en, bad_tr = f"{home} have had 97 shots.", f"{home} 97 şut çekti."
    model = FakeModel([[("get_score", {})], answer([good_en, bad_en], [good_tr, bad_tr]), answer([good_en, bad_en], [good_tr])])
    out = write_recap(rec, 60 * 60.0, 50, "HOME", "analyst", model, names, cache_dir=None)
    assert out["en"] == [good_en] and out["tr"] == [good_tr]
    assert out["source"] == {"en": "agent", "tr": "agent"}
    assert any("97" in r for r in out["reasons"]["en"])
    assert out["revised"] and "fix_these_problems" in model.inputs[-1]  # the agent got the Verifier's reasons once


def test_template_when_no_sentence_survives_or_the_model_fails(rec, names):
    model = FakeModel([[("get_score", {})], answer(["Northport have 99 corners."], ["Valemont yüzde 99."]), "not json"])
    out = write_recap(rec, 60 * 60.0, 50, None, "fan", model, names, cache_dir=None)
    assert out["source"] == {"en": "template", "tr": "template"}

    class Broken:
        name = "broken"

        def respond(self, input, previous_id):  # noqa: A002
            raise TimeoutError("model down")

    out = write_recap(rec, 60 * 60.0, 50, None, "fan", Broken(), names, cache_dir=None)
    assert out["source"] == {"en": "template", "tr": "template"} and "error" in out["reasons"]


def test_recap_request_gets_a_recap_message(monkeypatch):
    from htg.generate import OUT_DIR, generate
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", {})
    match_dir = OUT_DIR / "match_0001"
    match_dir = match_dir if match_dir.exists() else generate(1)
    meta = json.loads((match_dir / "meta.json").read_text())

    async def run() -> dict:
        async def handler(ws) -> None:
            await serve.session(ws, match_dir, meta, 30.0, 50.0, set())

        async with websockets.serve(handler, "localhost", 0, process_request=serve.process_request) as srv:
            async with websockets.connect(f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws") as c:
                assert json.loads(await asyncio.wait_for(c.recv(), 30))["type"] == "hello"
                await c.send(json.dumps({"type": "recap_request"}))
                while True:
                    m = json.loads(await asyncio.wait_for(c.recv(), 30))
                    if m["type"] == "recap":
                        return m

    m = asyncio.run(run())
    assert m["kind"] == "missed" and m["source"] == {"en": "template", "tr": "template"}  # no Azure in tests
    assert m["since_min"] == max(int(m["t"] // 60) - 10, 0) and len(m["text"]["en"]) >= 2
