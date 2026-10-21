"""Offline renderer: data/match.json -> stereo audio (sonification + Director-timed narration).

Sound language (kept deliberately small):
  ball ticks   - every 125 ms while the ball is in play
                 pitch  = danger (pentatonic, A3..A5)
                 pan    = flank, from the attacking team's point of view
                 timbre = team (REDS warm / BLUES hollow-bright)
                 volume = ball speed
  heartbeat    - pressure on the ball carrier (faster + louder = more pressure)
  crowd bed    - swells with danger
  event cues   - pass click, shot whoosh, save thud, whistle, goal swell
  earcon       - two-note bell whenever the favorite player is involved
  narration    - only in dead-ball or low-danger windows; everything else ducks under it

Usage: python3 render_audio.py [tr|en|key]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter, resample_poly

SR = 44100
ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "data" / "match.json").read_text())
RNG = np.random.default_rng(7)

PENTA = [220.0 * 2 ** (s / 12) for s in (0, 3, 5, 7, 10, 12, 15, 17, 19, 22, 24)]
VOICE = {"tr": "tr", "en": "en-gb"}


# ---------- primitives ----------
def env(n, attack=0.005, decay=0.1):
    t = np.arange(n) / SR
    a = np.minimum(1.0, t / max(attack, 1e-4))
    return a * np.exp(-t / decay)


def tone(freq, dur, harmonics, attack=0.005, decay=0.08):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = sum(amp * np.sin(2 * np.pi * freq * h * t) for h, amp in harmonics)
    return sig * env(n, attack, decay)


def noise(dur):
    return RNG.standard_normal(int(dur * SR))


def band(sig, lo, hi):
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], btype="band")
    return lfilter(b, a, sig)


def lowpass(sig, hi):
    b, a = butter(2, hi / (SR / 2), btype="low")
    return lfilter(b, a, sig)


TIMBRE = {
    "RED": [(1, 1.0), (2, 0.35)],             # warm
    "BLUE": [(1, 1.0), (3, 0.4), (5, 0.22)],   # hollow / brighter
}


class Mix:
    def __init__(self, dur):
        self.L = np.zeros(int(dur * SR) + SR)
        self.R = np.zeros_like(self.L)

    def add(self, sig, t, pan=0.0, gain=1.0):
        i = int(t * SR)
        if i >= len(self.L):
            return
        sig = sig[: len(self.L) - i] * gain
        th = (pan + 1) * np.pi / 4  # equal-power pan
        self.L[i:i + len(sig)] += sig * np.cos(th)
        self.R[i:i + len(sig)] += sig * np.sin(th)


# ---------- sound vocabulary ----------
def tick(team, danger):
    f = PENTA[min(len(PENTA) - 1, int(round(danger * (len(PENTA) - 1))))]
    return tone(f, 0.11, TIMBRE[team], decay=0.045)


def heartbeat():
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    f = 75 - 25 * t / 0.18
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.004, 0.06)


def click():
    return band(noise(0.02), 1500, 4500) * env(int(0.02 * SR), 0.001, 0.006)


def whoosh():
    n = int(0.35 * SR)
    s = band(noise(0.35), 600, 7000) * np.linspace(0.2, 1, n) * env(n, 0.05, 0.2)
    return s


def thud():
    return tone(85, 0.25, [(1, 1.0)], 0.002, 0.07) + 0.3 * lowpass(noise(0.25), 400) * env(int(0.25 * SR), 0.002, 0.05)


def whistle(dur=0.45):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 2900 + 120 * np.sin(2 * np.pi * 28 * t)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR)
    e = np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.05)
    return s * e


def earcon():
    return np.concatenate([tone(1318.5, 0.14, [(1, 1.0)], 0.003, 0.08),
                           tone(1975.5, 0.4, [(1, 1.0)], 0.003, 0.18)])


def goal_swell(team):
    n = int(3.5 * SR)
    crowd = lowpass(noise(3.5), 1800) * np.sin(np.pi * np.arange(n) / n) ** 0.7
    arp = np.zeros(n)
    for k, semis in enumerate((0, 4, 7, 12)):
        s = tone(440 * 2 ** (semis / 12), 0.5, TIMBRE[team], 0.01, 0.25)
        i = int(k * 0.13 * SR)
        arp[i:i + len(s)] += s
    return 0.6 * crowd + arp


def speak(text, lang):
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        subprocess.run(["espeak-ng", "-v", VOICE[lang], "-s", "168", "-p", "45", "-w", f.name, text],
                       check=True, capture_output=True)
        sr, s = wavfile.read(f.name)
    s = s.astype(np.float64) / 32768.0
    s = resample_poly(s, SR, sr)
    return s / (np.abs(s).max() + 1e-9)


# ---------- renderers ----------
def render_match(lang):
    meta, track, events = DATA["meta"], DATA["track"], DATA["events"]
    dur = meta["duration"] + 1.0
    son, voice = Mix(dur), Mix(dur)

    # crowd bed follows smoothed danger
    dang = np.interp(np.arange(int(dur * SR)) / SR,
                     [r["t"] for r in track], [r["danger"] for r in track])
    dang = lowpass(dang, 0.8)
    bed = lowpass(noise(dur), 900) * (0.025 + 0.09 * np.clip(dang, 0, 1))
    son.add(bed, 0.0)

    # ball ticks every 125 ms
    for t in np.arange(0, meta["duration"], 0.125):
        r = track[min(len(track) - 1, int(round(t * meta["hz"])))]
        if not r["in_play"]:
            continue
        vol = 0.10 + 0.14 * min(r["speed"] / 20.0, 1.0)
        son.add(tick(r["team"], r["danger"]), t, r["pan"], vol)

    # pressure heartbeat
    t = 0.0
    while t < meta["duration"]:
        r = track[min(len(track) - 1, int(round(t * meta["hz"])))]
        p = r["pressure"]
        if r["in_play"] and p > 0.15:
            son.add(heartbeat(), t, 0.0, 0.15 + 0.25 * p)
            t += 1.0 / (0.9 + 2.3 * p)
        else:
            t += 0.1

    # event cues
    for e in events:
        pan = next(r["pan"] for r in track if r["t"] >= e["t"] - 1e-9)
        ty = e["type"]
        if ty in ("pass", "cross", "clearance", "corner", "kickoff", "receive"):
            son.add(click(), e["t"], pan, 0.35)
        elif ty == "shot":
            son.add(whoosh(), e["t"] - 0.1, pan, 0.45)
        elif ty == "save":
            son.add(thud(), e["t"], pan, 0.6)
        elif ty == "out_corner":
            son.add(whistle(), e["t"] + 0.2, 0.0, 0.08)
        elif ty == "goal":
            son.add(goal_swell(e["team"]), e["t"], 0.0, 0.28)
            son.add(whistle(0.7), e["t"] + 0.6, 0.0, 0.07)
        if e["favorite"] and ty != "goal":
            son.add(earcon(), e["t"], pan, 0.10)

    # narration (Director windows) + ducking
    duck = np.ones(len(son.L))
    log = []
    for t0, text in DATA["narration"][lang]:
        s = speak(text, lang)
        voice.add(s, t0, 0.0, 0.85)
        i0, i1 = int(t0 * SR), int(t0 * SR) + len(s)
        duck[i0:i1] = 0.3
        log.append((t0, round(len(s) / SR, 2), text))
    duck = lowpass(duck, 4.0)

    L = son.L * duck + voice.L
    R = son.R * duck + voice.R
    return np.stack([L, R], axis=1), log


def render_key(lang="tr"):
    """A short 'sound dictionary' so a first-time listener knows what each sound means."""
    m = Mix(40.0)
    t = 0.3
    items = [
        ("Kırmızılar topta. Kaleye yaklaştıkça ses incelir.", "ticks_RED"),
        ("Maviler topta.", "ticks_BLUE"),
        ("Hücum eden takımın sol kanadı.", "pan_left"),
        ("Sağ kanadı.", "pan_right"),
        ("Rakip baskısı. Baskı arttıkça hızlanır.", "pressure"),
        ("Şut.", "shot"),
        ("Kurtarış.", "save"),
        ("Favori oyuncun topa dokundu.", "earcon"),
    ]
    for text, kind in items:
        s = speak(text, lang)
        m.add(s, t, 0.0, 0.85)
        t += len(s) / SR + 0.25
        if kind.startswith("ticks"):
            team = kind.split("_")[1]
            for k in range(16):
                m.add(tick(team, k / 15), t + k * 0.125, 0.0, 0.22)
            t += 2.3
        elif kind.startswith("pan"):
            p = -0.95 if kind.endswith("left") else 0.95
            for k in range(8):
                m.add(tick("RED", 0.4), t + k * 0.125, p, 0.22)
            t += 1.3
        elif kind == "pressure":
            tt, end = t, t + 4.0
            while tt < end:
                p = 0.15 + 0.85 * (tt - t) / 4.0
                m.add(heartbeat(), tt, 0.0, 0.25 + 0.45 * p)
                tt += 1.0 / (0.9 + 2.3 * p)
            t = end + 0.3
        elif kind == "shot":
            m.add(whoosh(), t, 0.0, 0.45); t += 0.8
        elif kind == "save":
            m.add(thud(), t, 0.0, 0.6); t += 0.8
        elif kind == "earcon":
            m.add(earcon(), t, 0.0, 0.12); t += 1.0
        t += 0.4
    n = int(t * SR)
    return np.stack([m.L[:n], m.R[:n]], axis=1)


def write(stereo, name):
    peak = np.abs(stereo).max()
    stereo = stereo / peak * 0.89  # -1 dBFS
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    wav = out / f"{name}.wav"
    wavfile.write(wav, SR, (stereo * 32767).astype(np.int16))
    mp3 = out / f"{name}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "160k", str(mp3)], check=True)
    print(f"{mp3}  ({len(stereo) / SR:.1f}s, pre-norm peak {peak:.2f})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "tr"
    if mode == "key":
        write(render_key(), "hear-the-game_ses-sozlugu")
    else:
        audio, log = render_match(mode)
        for t0, d, text in log:
            print(f"  narration @ {t0:5.1f}s  dur {d:4.1f}s  ends {t0 + d:5.1f}s  | {text}")
        write(audio, f"hear-the-game_mac_{mode}")
