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


def test_each_listener_gets_its_own_session():
    from services.engine import serve

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
