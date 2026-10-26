import asyncio
import json

import websockets

from services.engine.serve import process_request


class Req:
    def __init__(self, path: str):
        self.path = path


def test_http_routes():
    assert process_request(None, Req("/healthz")).status_code == 200
    page = process_request(None, Req("/?x=1"))
    assert page.status_code == 200 and b"<html" in page.body.lower()
    icon = process_request(None, Req("/apple-touch-icon.png"))
    assert icon.status_code == 200 and icon.body.startswith(b"\x89PNG")
    assert process_request(None, Req("/icon.svg")).headers["Content-Type"] == "image/svg+xml"
    manifest = json.loads(process_request(None, Req("/manifest.webmanifest")).body)
    assert all(process_request(None, Req("/" + i["src"])).status_code == 200 for i in manifest["icons"])
    assert process_request(None, Req("/nope")).status_code == 404
    assert process_request(None, Req("/callouts/en_normal_nope.mp3")).status_code == 404
    assert process_request(None, Req("/callouts/../../.env")).status_code == 404
    assert process_request(None, Req("/ws")) is None


def test_every_local_file_the_page_loads_is_served():
    import re

    from services.engine.serve import CLIENT

    refs = [r for r in re.findall(r'(?:href|src)="([^"]+)"', CLIENT.read_text()) if not r.startswith(("http", "#", "data:"))]
    kinds = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png"}
    assert any(r.endswith(".js") for r in refs) and "app.css" in refs
    for ref in refs:
        res = process_request(None, Req("/" + ref))
        assert res.status_code == 200, ref
        assert res.headers["Content-Type"].startswith(kinds[ref[ref.rindex("."):]]), ref
    assert process_request(None, Req("/js/../serve.py")).status_code == 404
    assert process_request(None, Req("/js/nope.js")).status_code == 404


def test_each_listener_gets_its_own_session_and_the_warm_up_runs_once(monkeypatch):
    from services.engine import serve

    calls = []
    real = serve.warm_up
    monkeypatch.setattr(serve, "_warm", serve.OrderedDict())
    monkeypatch.setattr(serve, "warm_up", lambda *a: (calls.append(1), real(*a)))

    async def run() -> list[str]:
        from htg.generate import OUT_DIR, generate

        match_dir = OUT_DIR / "match_0001"
        match_dir = match_dir if match_dir.exists() else generate(1)
        match, sessions = serve.Match.load(match_dir), set()

        async def handler(ws) -> None:
            await serve.session(ws, match, [[300.0, 5400.0]], 50.0, sessions)

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            uri = f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws"
            async with websockets.connect(uri) as a, websockets.connect(uri) as b:
                return [json.loads(await asyncio.wait_for(c.recv(), 10))["type"] for c in (a, b)]

    assert asyncio.run(run()) == ["hello", "hello"]
    assert len(calls) == 1  # the second listener got a copy of the warmed pipeline


def test_warm_up_does_not_block_the_event_loop(monkeypatch):
    import time

    from services.engine import serve

    monkeypatch.setattr(serve, "warm_up", lambda *a: time.sleep(0.3))
    monkeypatch.setattr(serve, "_warm", serve.OrderedDict())

    async def run() -> int:
        from htg.generate import OUT_DIR, generate

        match_dir = OUT_DIR / "match_0001"
        match_dir = match_dir if match_dir.exists() else generate(1)
        match = serve.Match.load(match_dir)

        async def handler(ws) -> None:
            await serve.session(ws, match, [[300.0, 5400.0]], 50.0, set())

        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            uri = f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws"
            async with websockets.connect(uri) as c:
                t = asyncio.create_task(ticker())
                await asyncio.wait_for(c.recv(), 10)  # hello arrives only after the (slow) warm-up
                t.cancel()
        return ticks

    assert asyncio.run(run()) >= 8  # a blocked loop would tick ~0 times during the 0.3 s warm-up


def test_query_picks_the_match_mode_and_start_second():
    from htg.league import DEFAULT_MATCH, fixture
    from services.engine.serve import from_of, mode_of, query

    assert fixture(query("/ws?match=northport-valemont", "match"))["seed"] == 7
    assert fixture(query("/ws?match=../etc", "match"))["id"] == fixture("")["id"] == DEFAULT_MATCH
    assert mode_of("/ws?mode=highlights") == "highlights" and mode_of("/ws?mode=x") == mode_of("/ws") == "live"
    assert from_of("/ws?from=1345.6", 5400.0) == 1345.0 and from_of("/ws", 5400.0) == 0.0
    assert from_of("/ws?from=-5", 5400.0) == 0.0 and from_of("/ws?from=99999", 5400.0) == 5399.0
    assert from_of("/ws?from=nan", 5400.0) == from_of("/ws?from=inf", 5400.0) == from_of("/ws?from=x", 5400.0) == 0.0


def run_session(match_dir, windows: list, speed: float, until: str, path: str = "/ws", mode: str = "live") -> list[dict]:
    """Messages of one session up to (and including) the first message of type `until`."""
    from services.engine import serve

    async def run() -> list[dict]:
        match = serve.Match.load(match_dir)

        async def handler(ws) -> None:
            await serve.session(ws, match, windows, speed, set(), mode=mode)

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            async with websockets.connect(f"ws://localhost:{srv.sockets[0].getsockname()[1]}{path}") as c:
                out = []
                while not out or out[-1]["type"] != until:
                    out.append(json.loads(await asyncio.wait_for(c.recv(), 30)))
                return out

    return asyncio.run(run())


def seed7():
    from htg.generate import OUT_DIR, generate

    match_dir = OUT_DIR / "match_0007"
    return match_dir if match_dir.exists() else generate(7)


def test_live_from_minute_76_starts_with_its_score_and_runs_to_full_time(monkeypatch):
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", serve.OrderedDict())
    match_dir = seed7()
    goals = [json.loads(line) for line in (match_dir / "events.jsonl").open() if '"type": "goal"' in line]
    expected = {"HOME": 0, "AWAY": 0}
    for g in goals:
        if g["t"] < 76 * 60:
            expected[g["team"]] += 1
    assert sum(expected.values()) >= 1  # seed 7: the first goal comes before minute 76
    hello = run_session(match_dir, [[76 * 60.0, 5400.0]], 50.0, "hello")[0]
    assert hello["score"] == expected and hello["windows"] == [[4560.0, 5400.0]] and hello["watch"] == "live"
    assert hello["match"] == "synth_0007" and {m["kind"] for m in hello["moments"]} >= {"goal", "save", "yellow"}
    # the match so far, for the timeline: Insights and shot / goal cues before 76', the first goal among them
    hist = hello["history"]
    assert {h["type"] for h in hist} == {"insight", "event_cue"} and all(serve.t_of(h) < 4560.0 for h in hist)
    assert [round(h["t"]) for h in hist if h["type"] == "event_cue" and h["kind"] == "goal"] == [1358]


def test_moments_and_highlight_windows():
    from services.engine.serve import highlight_windows, moments_of

    events = [{"t": 100.0, "type": "pass"}, {"t": 200.0, "type": "shot", "outcome": "saved", "team": "HOME"},
              {"t": 210.0, "type": "shot", "outcome": "blocked", "team": "AWAY"},
              {"t": 400.0, "type": "foul", "card": "yellow", "team": "AWAY"},
              {"t": 420.0, "type": "shot", "outcome": "goal", "team": "HOME"}, {"t": 420.5, "type": "goal", "team": "HOME"},
              {"t": 5390.0, "type": "foul", "card": "red", "team": "HOME"}]
    moments = moments_of(events)
    assert [(m["t"], m["kind"], m["team"]) for m in moments] == [(200.0, "save", "HOME"), (400.0, "yellow", "AWAY"),
                                                                  (420.0, "goal", "HOME"), (5390.0, "red", "HOME")]
    # 400 and 420 overlap and merge; the last window stops at full time
    assert highlight_windows(moments, 5400.0) == [[170.0, 216.0], [370.0, 436.0], [5360.0, 5400.0]]
    assert highlight_windows([{"t": 10.0}], 5400.0) == [[0.0, 26.0]]


def test_highlights_cut_to_the_next_clip_with_the_warm_up_score(monkeypatch):
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", serve.OrderedDict())
    match_dir = seed7()
    windows = [[1300.0, 1310.0], [4740.0, 4800.0]]  # before the first goal (22:38), then after it
    msgs = run_session(match_dir, windows, 100.0, "cut", mode="highlights")
    hello, cut = msgs[0], msgs[-1]
    assert hello["watch"] == "highlights" and hello["windows"] == windows
    hist = cut.pop("history")
    assert cut == {"type": "cut", "t_from": 1310.0, "t_to": 4740.0, "score": {"HOME": 0, "AWAY": 1}}
    assert hist and all(1310.0 < serve.t_of(h) < 4740.0 for h in hist)  # what happened between the two clips, goal included
    assert any(h["type"] == "event_cue" and h["kind"] == "goal" for h in hist)
    played = [p["t"] for m in msgs if m["type"] == "state" for p in m["packets"]]
    assert played and 1300.0 <= min(played) and max(played) <= 1310.0  # nothing from outside the clip


def test_stats_come_every_10_s_from_the_recap_tool(monkeypatch):
    from htg.generate import OUT_DIR, generate
    from htg.recap.tools import get_stats
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", serve.OrderedDict())
    match_dir = OUT_DIR / "match_0001"
    match_dir = match_dir if match_dir.exists() else generate(1)
    match = serve.Match.load(match_dir)

    async def run() -> tuple[dict, list[dict]]:
        async def handler(ws) -> None:
            await serve.session(ws, match, [[1800.0, 5400.0]], 100.0, set())

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            async with websockets.connect(f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws") as c:
                hello, stats = json.loads(await asyncio.wait_for(c.recv(), 30)), []
                while len(stats) < 3:
                    m = json.loads(await asyncio.wait_for(c.recv(), 30))
                    if m["type"] == "stats":
                        stats.append(m)
                return hello, stats

    hello, stats = asyncio.run(run())
    assert hello["windows"] == [[1800.0, 5400.0]]
    rec = serve.record_for(match_dir)
    assert [round(b["t"] - a["t"]) for a, b in zip(stats, stats[1:], strict=False)] == [10, 10]
    for m in stats:
        assert m["match"] == get_stats(rec, m["t"]) and m["last10"] == get_stats(rec, m["t"], from_min=m["t"] / 60 - 10)
        assert m["last10"]["length_min"] == 10 and m["match"]["from_minute"] == 0


def test_only_the_latest_valid_preference_of_each_type_is_kept():
    from services.engine.serve import keep_pref

    prefs: dict = {}
    junk = [{"type": "x", "n": i} for i in range(1000)] + [{"type": "set_mode", "mode": ["casual"]}, {"type": "set_mode", "mode": "nope"}]
    assert not any(keep_pref(prefs, m) for m in junk)
    assert keep_pref(prefs, {"type": "set_mode", "mode": "analyst"}) and keep_pref(prefs, {"type": "set_mode", "mode": "casual"})
    assert prefs == {"set_mode": {"type": "set_mode", "mode": "casual"}}
