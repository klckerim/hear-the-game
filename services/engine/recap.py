"""Turns a recap request into a `recap` message: agent text (or the template recap) and one Azure clip per language.

Never raises and never blocks the replay loop: past the deadline the listener gets the template recap, which needs no model.
"""
from __future__ import annotations

import asyncio
import base64
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from htg.adapters.base import Speech
from htg.recap.agent import CACHE_DIR, LANGS, RecapModel, template_recap, write_recap
from htg.recap.tools import MatchRecord
from services.engine.resolve import MP3_BYTES_PER_S

RECAP_TIMEOUT_S = 25.0  # the button says "Preparing..." meanwhile; measured agent latency is in eval/results/recap.md
MISSED_MIN = 10  # "What did I miss?" covers the last 10 minutes by default
# Recaps run here, not on the default pool narration and commentary use: a burst of recaps cannot starve them
RECAP_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recap")


def since_for(kind: str, t: float, since_min: Any = None) -> int:
    """Full time and half-time (Highlights): the whole match so far. Otherwise the asked minute (clamped to
    [0, now]) or the last MISSED_MIN minutes (also when it is missing, NaN or infinite)."""
    if kind in ("full_time", "half_time"):
        return 0
    now_min = int(t // 60)
    if isinstance(since_min, (int, float)) and not isinstance(since_min, bool) and math.isfinite(since_min):
        return int(min(max(since_min, 0), now_min))
    return max(now_min - MISSED_MIN, 0)


async def recap_message(rec: MatchRecord, model: RecapModel | None, speech: Speech, names: list[str], t: float, kind: str,
                        since_min: int, favourite: str | None, persona: str) -> dict[str, Any]:
    def work() -> tuple[dict, dict[str, bytes | None]]:
        # full-time (pre-generated for the demo) and half-time recaps are cached; a "missed" recap is asked at a new moment every time
        r = write_recap(rec, t, since_min, favourite, persona, model, names, CACHE_DIR if kind in ("full_time", "half_time") else None)
        return r, {lang: speech.synthesize(" ".join(r[lang]), lang) for lang in LANGS}

    try:
        r, audio = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(RECAP_POOL, work), RECAP_TIMEOUT_S)
    except Exception:  # timeout or anything unexpected: the template recap, no audio (the device voice reads it)
        text, _ = template_recap(rec, t, since_min)
        r, audio = {**text, "source": {lang: "template" for lang in LANGS}}, {lang: None for lang in LANGS}
    return {"type": "recap", "kind": kind, "t": t, "since_min": since_min, "persona": persona, "favourite": favourite,
            "text": {lang: r[lang] for lang in LANGS}, "source": r["source"],
            "audio": {lang: base64.b64encode(a).decode() if a else None for lang, a in audio.items()},
            "duration_s": {lang: round(len(a) / MP3_BYTES_PER_S, 1) if a else None for lang, a in audio.items()}}
