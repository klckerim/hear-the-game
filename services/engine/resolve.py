"""Turns a template `speech` message into the final one: verified model text and audio from cache or Azure, within a deadline.

Never raises and never blocks the replay loop: on timeout or error the client gets the template text and no audio.
"""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

from htg.adapters.base import Narrator, Speech
from htg.narration.service import narrate_insight
from htg.telemetry import resolve_ms, speech_resolved

LANGS = ("en", "tr")
TIMEOUT_S = 4.0
MAX_LATE_S = 8.0  # a non-goal speech resolved later than this (match time) is dropped
MP3_BYTES_PER_S = 48_000 / 8  # Audio24Khz48KBitRateMonoMp3


def is_stale(msg: dict, now_t: float) -> bool:
    return msg["priority"] < 5 and now_t - msg["t"] > MAX_LATE_S


class SpeechResolver:
    def __init__(self, narrator: Narrator, speech: Speech, names: list[str], use_service: bool, timeout: float = TIMEOUT_S):
        self.narrator, self.speech, self.names, self.use_service, self.timeout = narrator, speech, names, use_service, timeout

    def _work(self, insight: dict) -> tuple[dict, dict[str, bytes | None]]:
        n = narrate_insight(insight, self.narrator, self.names)
        return n, {lang: self.speech.synthesize(n[lang], lang, insight["type"] == "goal") for lang in LANGS}

    async def resolve(self, msg: dict, insight: dict) -> dict[str, Any]:
        t0 = time.perf_counter()
        n, audio = None, {lang: None for lang in LANGS}
        if self.use_service:
            try:
                n, audio = await asyncio.wait_for(asyncio.to_thread(self._work, insight), self.timeout)
            except Exception:  # timeout, model or network error: template text, no audio
                n = None
        text = {lang: n[lang] for lang in LANGS} if n else msg["text"]
        source = n["source"] if n else {lang: "template" for lang in LANGS}
        for lang in LANGS:
            speech_resolved.add(1, {"source": "cache" if n and n["cached"] and source[lang] == "llm" else source[lang], "lang": lang})
        resolve_ms.record((time.perf_counter() - t0) * 1000)
        return {**msg, "text": text, "source": source,
                "audio": {lang: base64.b64encode(a).decode() if a else None for lang, a in audio.items()},
                "duration_s": {lang: round(len(a) / MP3_BYTES_PER_S, 1) if a else None for lang, a in audio.items()}}
