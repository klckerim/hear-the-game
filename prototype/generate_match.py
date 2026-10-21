"""Synthetic 60-second match excerpt for the Hear the Game prototype.

Produces data/match.json with:
  - events: discrete actions (pass, carry, cross, shot, save, out, goal, kickoff)
  - track:  10 Hz ball state (x, y, team in possession, in_play, danger, pressure, pan, speed)
  - narration: Director-approved speech slots (only in dead-ball or low-danger windows)

Coordinates: pitch 105 x 68 m, global broadcast frame.
REDS attack towards x=105, BLUES attack towards x=0.
All teams and players are fictional.
"""
import json
import math
from pathlib import Path

import numpy as np

HZ = 10
DURATION = 60.0
OUT = Path(__file__).parent / "data" / "match.json"

# (t, x, y, team, player, event_type, in_play_after)
KEYFRAMES = [
    # Phase A - Reds build up, Blues press, switch of play, shot saved
    (0.0, 30.0, 34.0, "RED", "Demir", "kickoff_possession", True),
    (1.5, 38.0, 62.0, "RED", "Aksoy", "pass", True),
    (3.5, 48.0, 63.0, "RED", "Aksoy", "carry", True),
    (5.0, 56.0, 40.0, "RED", "Kaya", "pass", True),
    (6.0, 58.0, 38.0, "RED", "Kaya", "carry", True),
    (7.5, 70.0, 10.0, "RED", "Yildiz", "pass", True),
    (10.0, 82.0, 8.0, "RED", "Yildiz", "carry", True),
    (11.5, 96.0, 32.0, "RED", "Arda", "cross", True),
    (11.9, 104.0, 36.0, "RED", "Arda", "shot", True),
    (11.95, 104.0, 36.0, "BLUE", "Keeper", "save", True),
    (12.6, 105.0, 20.0, "BLUE", "Keeper", "out_corner", False),
    # dead ball 12.6 - 20.5, ball placed at corner spot
    (20.0, 105.0, 0.5, "RED", "Yildiz", "placed", False),
    # Phase B - corner cleared, Blues counter, goal
    (20.5, 105.0, 0.5, "RED", "Yildiz", "corner", True),
    (21.6, 99.0, 32.0, "BLUE", "Moreau", "clearance", True),
    (22.6, 80.0, 40.0, "BLUE", "Silva", "receive", True),
    (23.4, 74.0, 38.0, "BLUE", "Silva", "carry", True),
    (25.0, 52.0, 14.0, "BLUE", "Okafor", "pass", True),
    (27.2, 34.0, 20.0, "BLUE", "Okafor", "carry", True),
    (29.0, 22.0, 30.0, "BLUE", "Okafor", "carry", True),
    (29.35, 0.0, 32.0, "BLUE", "Okafor", "shot", True),
    (29.4, 0.0, 32.0, "BLUE", "Okafor", "goal", False),
    # dead ball until kickoff
    (39.5, 52.5, 34.0, "RED", "Kaya", "placed", False),
    # Phase C - Reds recycle possession, calm
    (40.0, 52.5, 34.0, "RED", "Kaya", "kickoff", True),
    (41.5, 40.0, 30.0, "RED", "Demir", "pass", True),
    (43.5, 30.0, 50.0, "RED", "Demir", "pass", True),
    (46.0, 28.0, 20.0, "RED", "Aksoy", "pass", True),
    (48.5, 38.0, 12.0, "RED", "Kaya", "pass", True),
    (51.0, 45.0, 28.0, "RED", "Kaya", "pass", True),
    (53.5, 36.0, 44.0, "RED", "Demir", "pass", True),
    (56.0, 42.0, 58.0, "RED", "Aksoy", "pass", True),
    (58.5, 50.0, 40.0, "RED", "Kaya", "pass", True),
    (60.0, 54.0, 36.0, "RED", "Kaya", "carry", True),
]

# Pressure on the ball carrier (0..1), piecewise linear (t, value)
PRESSURE = [(0, 0.2), (5, 0.5), (6, 0.75), (10, 0.95), (12, 0.8), (12.6, 0.0),
            (20.5, 0.0), (21.6, 0.3), (25, 0.2), (28, 0.45), (29.4, 0.5), (29.5, 0.0),
            (40, 0.0), (40.1, 0.1), (60, 0.1)]

FAVORITE_PLAYER = "Okafor"

NARRATION = {
    "tr": [
        (13.2, "Kaleci kurtardı, korner. Mavilerin presi arttı. Kırmızılar oyunu sağa çevirdi."),
        (31.2, "Gol! Maviler, Okafor. Kornerden gole sekiz saniye. Kırmızılar arkada iki kişi kalmıştı."),
        (45.5, "Tempo düştü. Kırmızılar kendi yarı sahasında topu çeviriyor."),
    ],
    "en": [
        (13.2, "Saved, corner. The Blues pressed harder, so the Reds switched play to the right."),
        (31.2, "Goal for the Blues! Okafor. Eight seconds from the corner. The Reds were left with two at the back."),
        (45.5, "The tempo drops. The Reds are recycling the ball in their own half."),
    ],
}


def attacking_frame(x, y, team):
    """Return (distance to the goal being attacked, flank pan) for the team in possession.

    pan: -1 = attacker's left flank, +1 = attacker's right flank.
    """
    if team == "RED":
        gx, pan = 105.0, -(y - 34.0) / 34.0
    else:
        gx, pan = 0.0, (y - 34.0) / 34.0
    return math.hypot(gx - x, 34.0 - y), max(-1.0, min(1.0, pan))


def danger(x, y, team):
    """xT-like proxy: decays with distance to goal, rewards central angle."""
    d, _ = attacking_frame(x, y, team)
    gx = 105.0 if team == "RED" else 0.0
    ang = math.atan2(abs(34.0 - y), abs(gx - x) + 1e-6)
    return float(np.clip(math.exp(-d / 24.0) * (0.55 + 0.45 * math.cos(ang)) * 1.6, 0, 1))


def interp(series, t):
    ts, vs = zip(*series)
    return float(np.interp(t, ts, vs))


def build():
    times = np.round(np.arange(0, DURATION + 1e-9, 1 / HZ), 2)
    kf_t = [k[0] for k in KEYFRAMES]
    track = []
    prev = None
    for t in times:
        i = max(j for j, kt in enumerate(kf_t) if kt <= t + 1e-9)
        k0 = KEYFRAMES[i]
        k1 = KEYFRAMES[min(i + 1, len(KEYFRAMES) - 1)]
        if k1[0] > k0[0] and k0[6]:
            a = (t - k0[0]) / (k1[0] - k0[0])
            x, y = k0[1] + a * (k1[1] - k0[1]), k0[2] + a * (k1[2] - k0[2])
        else:
            x, y = k0[1], k0[2]
        team = k0[3] if k0[5] not in ("save", "out_corner") else "BLUE"
        in_play = bool(k0[6])
        speed = 0.0 if prev is None else math.hypot(x - prev[0], y - prev[1]) * HZ
        _, pan = attacking_frame(x, y, team)
        track.append({
            "t": float(t), "x": round(x, 2), "y": round(y, 2), "team": team,
            "in_play": in_play,
            "danger": round(danger(x, y, team), 3) if in_play else 0.0,
            "pressure": round(interp(PRESSURE, t), 3) if in_play else 0.0,
            "pan": round(pan, 3), "speed": round(speed, 2),
        })
        prev = (x, y)

    events = [{"t": k[0], "x": k[1], "y": k[2], "team": k[3], "player": k[4],
               "type": k[5], "favorite": k[4] == FAVORITE_PLAYER}
              for k in KEYFRAMES if k[5] != "placed"]

    data = {
        "meta": {"hz": HZ, "duration": DURATION, "pitch": [105, 68],
                 "teams": {"RED": "attacks right", "BLUE": "attacks left"},
                 "favorite_player": FAVORITE_PLAYER, "synthetic": True},
        "events": events, "track": track, "narration": NARRATION,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {OUT} | {len(track)} frames | {len(events)} events")
    peak = max(track, key=lambda r: r["danger"])
    print(f"peak danger {peak['danger']} at t={peak['t']} team={peak['team']}")


if __name__ == "__main__":
    build()
