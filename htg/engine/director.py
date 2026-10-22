"""Director: decides which queued Insight is told now. Pure: no I/O, no clock; time comes from the caller.

Rules, in order, for each Insight in the queue:
1. expired (`now > expires_at`)             -> drop
   chance from danger alone (no shot)       -> drop (the sound already carries danger; by the time the ball is quiet it is stale)
2. goal                                     -> speak immediately (no other rule applies)
3. same type and team spoken < 5 min ago    -> drop
4. ball live and danger >= 0.15             -> hold (never talk over an attack)
5. silence budget of the mode not yet over  -> hold
Only one Insight is spoken per call: highest priority first, then oldest. The rest are held for the next call.
The listener's favourite club (if any) gets +1 priority for its Insights.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

DANGER_QUIET = 0.15
REPEAT_S = 300.0
# Minimum silence between two spoken Insights, per listening mode. Goals ignore it.
SILENCE_S = {"eyes_free": 10.0, "casual": 25.0, "analyst": 15.0}

Action = Literal["speak", "hold", "drop"]


@dataclass(frozen=True)
class Decision:
    action: Action
    insight: dict[str, Any]
    reason: str


def decide(queue: Sequence[dict], state: dict, now: float, mode: str = "casual",
           spoken: Sequence[tuple[float, str, str | None]] = (), favourite: str | None = None) -> list[Decision]:
    """One Decision per queued Insight. `spoken` is the history of what was told: (t, type, team). `favourite` is "HOME", "AWAY" or None."""
    if mode not in SILENCE_S:
        raise ValueError(f"unknown mode: {mode}")
    last_spoken = max((t for t, _, _ in spoken), default=-1e9)
    quiet = not state["in_play"] or state["danger"] < DANGER_QUIET
    out: dict[str, Decision] = {}
    ready: list[dict] = []
    for ins in queue:
        key = ins["insight_id"]
        if now > ins["expires_at"]:
            out[key] = Decision("drop", ins, "expired")
        elif ins["type"] == "chance" and ins["claim_facts"].get("source") == "danger":
            out[key] = Decision("drop", ins, "sound carries danger")
        elif ins["type"] == "goal":
            ready.append(ins)
        elif any(ty == ins["type"] and tm == ins["team"] and now - t < REPEAT_S for t, ty, tm in spoken):
            out[key] = Decision("drop", ins, "repeat")
        elif not quiet:
            out[key] = Decision("hold", ins, "ball is dangerous")
        elif now - last_spoken < SILENCE_S[mode]:
            out[key] = Decision("hold", ins, "silence budget")
        else:
            ready.append(ins)
    ready.sort(key=lambda i: (-i["priority"] - (favourite is not None and i["team"] == favourite), i["t"]))
    for k, ins in enumerate(ready):
        if k == 0:
            out[ins["insight_id"]] = Decision("speak", ins, "goal" if ins["type"] == "goal" else "ok")
        else:
            out[ins["insight_id"]] = Decision("hold", ins, "one at a time")
    return [out[i["insight_id"]] for i in queue]
