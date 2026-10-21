"""Measure the deployed demo from the outside, like a listener's browser would see it.

    python -m eval.latency --url wss://<app>/ws --sessions 1 --minutes 3
    python -m eval.latency --url wss://<app>/ws --sessions 10 --minutes 3
    python -m eval.latency --url wss://<app>/ws --sessions 1 --minutes 3 --mode analyst   # more cache misses: live Foundry calls

Each run appends one section to eval/results/latency.md. Measured per session: connect -> `hello`; wall-clock gap between
`state` messages (nominal: one batch per 200 ms of match time); decision -> `speech` (the server's resolve delay: cache, or
Foundry + Speech within the 4 s deadline); `insight` -> `speech` (includes the Director holding the Insight back); share of
`speech` by source. Client audio output latency is not measured.
"""
from __future__ import annotations

import argparse
import asyncio
import bisect
import datetime
import json
import time
from pathlib import Path

import websockets

RESULTS = Path(__file__).resolve().parent / "results" / "latency.md"
NOMINAL_STATE_MS = 200


async def one_session(url: str, minutes: float, mode: str) -> dict:
    """Listens for `minutes` of wall-clock time; returns raw timings in seconds (wall clock is fine here: eval, not htg/)."""
    out: dict = {"hello": None, "state": [], "speech": [], "insight": {}, "error": None}
    state_t: list[float] = []  # last match time in each state batch, with its arrival in `out["state"]`
    t0 = time.perf_counter()
    try:
        async with websockets.connect(url, max_size=None, open_timeout=30) as ws:
            if mode != "casual":
                await ws.send(json.dumps({"type": "set_mode", "mode": mode}))
            end = t0 + 60 * minutes
            while (left := end - time.perf_counter()) > 0:
                try:
                    raw = await asyncio.wait_for(ws.recv(), left)
                except TimeoutError:
                    break
                now, msg = time.perf_counter(), json.loads(raw)
                kind = msg.get("type")
                if kind == "hello" and out["hello"] is None:
                    out["hello"] = now - t0
                elif kind == "state" and msg.get("packets"):
                    out["state"].append(now)
                    state_t.append(msg["packets"][-1]["t"])
                elif kind == "insight":
                    out["insight"][msg["insight"]["insight_id"]] = now
                elif kind == "speech":
                    k = bisect.bisect_left(state_t, msg["t"])  # first batch that reached the decision's match time
                    decided = out["state"][k] if k < len(state_t) else None
                    audio = {lg: bool(a) for lg, a in (msg.get("audio") or {}).items()}
                    out["speech"].append({"arrived": now, "decided": decided, "insight": out["insight"].get(msg["insight_id"]),
                                          "source": msg.get("source", {}), "audio": audio})
    except Exception as e:  # report, do not crash the other sessions
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    return out


def q(xs: list[float], unit: str = "ms") -> str:
    """p50 / p95 / max, in ms."""
    if not xs:
        return "n/a"
    xs = sorted(1000 * x for x in xs)
    p = lambda f: xs[min(len(xs) - 1, int(f * len(xs)))]  # noqa: E731
    return f"{p(0.5):.0f} / {p(0.95):.0f} / {xs[-1]:.0f} {unit}"


def report(runs: list[dict], url: str, sessions: int, minutes: float, mode: str, client: str, region: str) -> list[str]:
    hello = [r["hello"] for r in runs if r["hello"] is not None]
    gaps = [b - a for r in runs for a, b in zip(r["state"], r["state"][1:], strict=False)]
    speech = [s for r in runs for s in r["speech"]]
    resolve = [s["arrived"] - s["decided"] for s in speech if s["decided"] is not None]
    held = [s["arrived"] - s["insight"] for s in speech if s["insight"] is not None]
    errors = [r["error"] for r in runs if r["error"]]
    target = "a local server" if "localhost" in url else "the deployed Container App"  # the public URL stays out of the repo
    rows = [f"### {datetime.date.today().isoformat()}: {sessions} session(s), {minutes:g} min, mode `{mode}`", "",
            f"Client: {client} -> {region}. Target: {target}. Sessions started together; each replays the demo match from minute 13.", "",
            "| measure | n | p50 / p95 / max |", "|---|---|---|",
            f"| connect -> `hello` | {len(hello)} | {q(hello)} |",
            f"| `state` inter-arrival (nominal {NOMINAL_STATE_MS} ms) | {len(gaps)} | {q(gaps)} |",
            f"| decision -> `speech` (server resolve, approx. +/- one state batch) | {len(resolve)} | {q(resolve)} |",
            f"| `insight` -> `speech` (incl. Director hold) | {len(held)} | {q(held)} |", ""]
    for lang in ("en", "tr"):
        src: dict[str, int] = {}
        for s in speech:
            src[s["source"].get(lang, "?")] = src.get(s["source"].get(lang, "?"), 0) + 1
        audio = sum(s["audio"].get(lang, False) for s in speech)
        share = ", ".join(f"{k} {v} ({100 * v / len(speech):.0f}%)" for k, v in sorted(src.items())) if speech else "none"
        rows.append(f"- `speech` {lang.upper()} by source: {share}; with audio: {audio} of {len(speech)}")
    rows.append(f"- Session errors: {len(errors)}" + (f" ({'; '.join(sorted(set(errors)))})" if errors else ""))
    return rows + [""]


HEADER = """# Deployed latency

Measured from outside with `python -m eval.latency` (see the module docstring). What this does **not** measure:

- Client audio latency (Web Audio scheduling, Bluetooth headphones). The client also adds a fixed 300 ms jitter buffer on purpose.
- Cache hit vs live model call: the `speech` message only says `llm` (verified) or `template`. The split is in the App Insights
  metric `htg.speech.resolved` (source cache / llm / template).
- Speech dropped as stale (resolved more than 8 s of match time late) never reaches the client; it is counted only in the
  App Insights metric `htg.speech.dropped_stale`.

"""


def main(url: str, sessions: int, minutes: float, mode: str, client: str, region: str, out: Path) -> None:
    async def run() -> list[dict]:
        return await asyncio.gather(*(one_session(url, minutes, mode) for _ in range(sessions)))

    lines = report(asyncio.run(run()), url, sessions, minutes, mode, client, region)
    print("\n".join(lines))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(("" if out.exists() and out.stat().st_size else HEADER) + "\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--sessions", type=int, default=1)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--mode", choices=["eyes_free", "casual", "analyst"], default="casual")
    ap.add_argument("--client", default="Istanbul")
    ap.add_argument("--region", default="Sweden Central")
    ap.add_argument("--out", type=Path, default=RESULTS)
    a = ap.parse_args()
    main(a.url, a.sessions, a.minutes, a.mode, a.client, a.region, a.out)
