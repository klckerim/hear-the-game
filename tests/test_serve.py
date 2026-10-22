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


def test_each_listener_gets_its_own_session_and_the_warm_up_runs_once(monkeypatch):
    from services.engine import serve

    calls = []
    real = serve.warm_up
    monkeypatch.setattr(serve, "_warm", {})
    monkeypatch.setattr(serve, "warm_up", lambda *a: (calls.append(1), real(*a)))

    async def run() -> list[str]:
        from htg.generate import OUT_DIR, generate

        match_dir = OUT_DIR / "match_0001"
        match_dir = match_dir if match_dir.exists() else generate(1)
        meta = json.loads((match_dir / "meta.json").read_text())
        sessions: set = set()

        async def handler(ws) -> None:
            await serve.session(ws, match_dir, meta, 5.0, 50.0, sessions)

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
    monkeypatch.setattr(serve, "_warm", {})

    async def run() -> int:
        from htg.generate import OUT_DIR, generate

        match_dir = OUT_DIR / "match_0001"
        match_dir = match_dir if match_dir.exists() else generate(1)
        meta = json.loads((match_dir / "meta.json").read_text())

        async def handler(ws) -> None:
            await serve.session(ws, match_dir, meta, 5.0, 50.0, set())

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


def test_unknown_chapter_falls_back_to_the_default():
    from services.engine.serve import CHAPTERS, DEFAULT_CHAPTER, chapter_of

    assert chapter_of("/ws?chapter=late") == "late" and CHAPTERS["late"] == 76.0
    assert chapter_of("/ws") == chapter_of("/ws?chapter=../etc") == chapter_of("/ws?chapter=") == DEFAULT_CHAPTER


def test_late_chapter_starts_with_the_score_of_minute_76(monkeypatch):
    from htg.generate import OUT_DIR, generate
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", {})
    match_dir = OUT_DIR / "match_0007"
    match_dir = match_dir if match_dir.exists() else generate(7)
    meta = json.loads((match_dir / "meta.json").read_text())
    goals = [json.loads(line) for line in (match_dir / "events.jsonl").open() if '"type": "goal"' in line]
    expected = {"HOME": 0, "AWAY": 0}
    for g in goals:
        if g["t"] < 76 * 60:
            expected[g["team"]] += 1
    assert sum(expected.values()) >= 1  # seed 7: the first goal comes before the late chapter

    async def run() -> dict:
        async def handler(ws) -> None:
            await serve.session(ws, match_dir, meta, serve.CHAPTERS[serve.chapter_of(ws.request.path)], 50.0, set())

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            uri = f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws?chapter=late"
            async with websockets.connect(uri) as c:
                return json.loads(await asyncio.wait_for(c.recv(), 30))

    hello = asyncio.run(run())
    assert hello["type"] == "hello" and hello["score"] == expected
    assert hello["window"] == [76 * 60.0, meta["duration_s"]]  # the timeline ends at 90', not at 76' + 15


def test_stats_come_every_10_s_from_the_recap_tool(monkeypatch):
    from htg.generate import OUT_DIR, generate
    from htg.recap.tools import get_stats
    from services.engine import serve

    monkeypatch.setattr(serve, "_warm", {})
    match_dir = OUT_DIR / "match_0001"
    match_dir = match_dir if match_dir.exists() else generate(1)
    meta = json.loads((match_dir / "meta.json").read_text())

    async def run() -> tuple[dict, list[dict]]:
        async def handler(ws) -> None:
            await serve.session(ws, match_dir, meta, 30.0, 100.0, set())

        async with websockets.serve(handler, "localhost", 0, process_request=process_request) as srv:
            async with websockets.connect(f"ws://localhost:{srv.sockets[0].getsockname()[1]}/ws") as c:
                hello, stats = json.loads(await asyncio.wait_for(c.recv(), 30)), []
                while len(stats) < 3:
                    m = json.loads(await asyncio.wait_for(c.recv(), 30))
                    if m["type"] == "stats":
                        stats.append(m)
                return hello, stats

    hello, stats = asyncio.run(run())
    assert hello["window"] == [1800.0, 1800.0 + serve.END_AFTER_S]
    rec = serve.record_for(match_dir)
    assert [round(b["t"] - a["t"]) for a, b in zip(stats, stats[1:], strict=False)] == [10, 10]
    for m in stats:
        assert m["match"] == get_stats(rec, m["t"]) and m["last10"] == get_stats(rec, m["t"], from_min=m["t"] / 60 - 10)
        assert m["last10"]["length_min"] == 10 and m["match"]["from_minute"] == 0


def test_next_moment_starts_30_s_before_the_next_goal_save_or_card():
    from services.engine.serve import moments_of, start_minute_of

    events = [{"t": 100.0, "type": "pass"}, {"t": 200.0, "type": "shot", "outcome": "saved"},
              {"t": 210.0, "type": "shot", "outcome": "blocked"}, {"t": 400.0, "type": "foul", "card": "yellow"},
              {"t": 1300.0, "type": "shot", "outcome": "goal"}, {"t": 1300.5, "type": "goal"}]
    moments = moments_of(events)
    assert moments == [200.0, 400.0, 1300.0]
    assert start_minute_of("/ws?chapter=kickoff", moments) == 0.0  # no `next`: the chapter
    assert start_minute_of("/ws?chapter=kickoff&next=1", moments) * 60 == 170.0  # from the chapter start
    assert start_minute_of("/ws?chapter=kickoff&next=1&after=175", moments) * 60 == 370.0  # pressing again moves on
    assert start_minute_of("/ws?chapter=kickoff&next=1&after=1290", moments) == 0.0  # none left: the chapter
    assert start_minute_of("/ws?chapter=late&next=1&after=x", moments) == 76.0
