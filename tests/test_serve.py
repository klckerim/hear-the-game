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
    assert process_request(None, Req("/nope")).status_code == 404
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
