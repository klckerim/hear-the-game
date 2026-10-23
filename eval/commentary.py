"""Measure the live commentary layer: how often the match talks, before and after callouts and the commentator.

    HTG_ENV=azure python -m eval.commentary                                   # seed 7 chapters + seeds 11-15 from 19'
    HTG_ENV=azure python -m eval.commentary --windows 7:19 --minutes 3 --out /tmp/c.md   # a quick try

Each window replays 15 minutes of match time like a fan-mode session (Casual, 20 s delay, English listener). The commentator runs
for real (Foundry + Verifier + MAI-Voice, no cache) on a simulated clock: one segment at a time, a backlog skips to the newest
finished segment, and a line ready later than its play time + delay - 3 s is dropped, as in `services/engine/commentary.py`.
Playback follows the client's one-voice rules, simplified: narration first; a commentator line waits up to 3 s for a busy voice,
else it is dropped (a goal line cuts in); a callout is skipped while anything speaks, at most one every 2 s, a name at most every 3 s.
Durations: commentator clips from their MP3 size; narration from its English template at 2.5 words per second; callouts 0.55 s per
clip. "Speech" below means any of these playing; the ball sounds are not counted.
"""
from __future__ import annotations

import argparse
import datetime
import json
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from htg.commentary.commentator import COMMENTARY_PROMPT_VERSION, SPEECH_STYLE, WORDS_PER_S, commentate, get_commentator
from htg.env import load_env
from htg.generate import OUT_DIR, generate
from htg.narration.service import known_names
from htg.replay import iter_items
from services.engine.commentary import LATE_MARGIN_S
from services.engine.resolve import MP3_BYTES_PER_S
from services.engine.run_local import LivePipeline, warm_up

RESULTS = Path(__file__).resolve().parent / "results" / "commentary.md"
WINDOWS = [(7, 0.0), (7, 19.0), (7, 76.0), (11, 19.0), (12, 19.0), (13, 19.0), (14, 19.0), (15, 19.0)]
DELAY_S = 20.0
WAIT_S = 3.0  # COMM_WAIT_S in the client
CALL_GAP_S, NAME_EVERY_S, CALL_CLIP_S = 2.0, 3.0, 0.55
CALL_PRI = {"goal": 9, "shot": 8, "save": 7, "card": 6, "foul": 5, "corner": 4, "free_kick": 3, "throw_in": 2, "goal_kick": 1, "out": 1,
            "name": 0}
BIN_S = 30.0


@dataclass
class Voice:
    t: float
    dur: float
    kind: str
    goal: bool = False


def match_dir(seed: int) -> Path:
    d = OUT_DIR / f"match_{seed:04d}"
    return d if d.exists() else generate(seed)


def collect(seed: int, start: float, minutes: float) -> dict:
    """Narration, cues (with the ball's last frame) and segments of one window, from the same pipeline the server runs."""
    d = match_dir(seed)
    meta = json.loads((d / "meta.json").read_text())
    pipe = LivePipeline(meta, "casual", float("inf"))
    warm_up(pipe, d, start)
    t0 = start * 60.0
    t1 = min(t0 + minutes * 60.0, meta.get("duration_s", float("inf")))
    narr, cues, segs, goals, cur = [], [], [], set(), None
    for item in iter_items(d, start):
        if item.t > t1:
            break
        for m in pipe.feed(item):
            if m["type"] == "state":
                cur = m["packets"][-1]
            elif m["type"] == "event_cue":
                cues.append((m, cur))
            elif m["type"] == "insight" and m["insight"]["type"] == "goal":
                goals.add(m["insight"]["insight_id"])
            elif m["type"] == "speech":
                narr.append(Voice(m["t"], len(m["text"]["en"].split()) / WORDS_PER_S, "narration", m["insight_id"] in goals))
            elif m["type"] == "segment":
                segs.append(m["segment"])
    return {"seed": seed, "start": start, "t0": t0, "t1": t1, "meta": meta, "narr": narr, "cues": cues, "segs": segs}


def run_commentator(segs: list, model, speech, names: list[str]) -> dict:  # noqa: ANN001
    """The server's sequential stream on a simulated clock (speed 1: one match second per wall second)."""
    clock, i, recent, lines = float("-inf"), 0, [], []
    n = {"segments": 0, "skipped": 0, "errors": 0, "silent": 0, "dropped": 0, "en_failed": 0, "tr_failed": 0, "late": 0,
         "timeouts": 0}
    latency: list[float] = []
    while i < len(segs):
        clock = max(clock, segs[i].t1)
        j = max(k for k in range(i, len(segs)) if segs[k].t1 <= clock)
        n["skipped"] += j - i
        seg, i = segs[j], j + 1
        n["segments"] += 1
        budget = seg.t1 + DELAY_S - LATE_MARGIN_S - clock  # the server's wait_for: past it the stream gives up and moves on
        t_start = time.perf_counter()
        try:
            out = commentate(seg, model, names, recent)
            clips = [speech.commentate(line["en"], "en", SPEECH_STYLE["en"][line["style"]]) if line["en"] else None
                     for line in out["lines"]]
        except Exception:
            n["errors"] += 1
            clock += time.perf_counter() - t_start
            continue
        lat = time.perf_counter() - t_start
        latency.append(lat)
        if lat > budget:
            n["timeouts"] += 1
            clock += budget
            continue
        clock += lat
        n["dropped"] += out["dropped"]
        n["en_failed"] += sum(line["en"] is None for line in out["lines"]) + out["dropped"]
        n["tr_failed"] += sum(line["tr"] is None for line in out["lines"]) + out["dropped"]
        if not out["lines"]:
            n["silent"] += 1
        for line, clip in zip(out["lines"], clips, strict=True):
            if line["en"] is None:
                continue
            t = seg.t1 + line["offset_s"]
            if clock > t + DELAY_S - LATE_MARGIN_S:
                n["late"] += 1
                continue
            dur = len(clip) / MP3_BYTES_PER_S if clip else len(line["en"].split()) / WORDS_PER_S
            lines.append({"t": round(t, 2), "dur": round(dur, 2), "goal": seg.goal, "style": line["style"], "en": line["en"],
                          "tr": line["tr"], "latency_s": round(lat, 2), "segment": seg.segment_id})
            recent = (recent + [line["en"]])[-3:]
    return {"lines": lines, "counts": n, "latency": latency}


def callout_for(cue: dict, frame: dict | None, name_t: float) -> tuple[int, int, bool] | None:
    """(priority, clips, is_name) for one cue, as `calloutFor` in the client; None = no callout."""
    k = cue["kind"]
    if k == "goal":
        return CALL_PRI["goal"], 2, False
    if k == "shot" and cue.get("outcome") != "goal":
        return CALL_PRI["shot"], 2 + (cue.get("outcome") in ("saved", "blocked", "off_target")), True
    if k == "foul":
        return (CALL_PRI["card"], 3, False) if cue.get("card") else (CALL_PRI["foul"], 1, False)
    if k == "restart" and cue.get("restart") in CALL_PRI:
        return CALL_PRI[cue["restart"]], 2, False
    if k == "out":
        return CALL_PRI["out"], 1, False
    team = cue["team"]
    final_third = frame and frame.get("in_play") and frame.get("team") == team and (frame["x"] >= 70 if team == "HOME"
                                                                                    else frame["x"] <= 35)
    if k == "pass" and cue.get("player_id") and cue["t"] - name_t >= NAME_EVERY_S and final_third:
        return CALL_PRI["name"], 1, True
    return None


def playback(w: dict, comm: list[dict], callouts: bool) -> tuple[list[tuple[float, float]], int]:
    """What the listener hears: (start, end) of every voice, and the commentator lines dropped because the voice was taken."""
    todo = [(v.t, 0, v) for v in w["narr"]]
    todo += [(c["t"], 1, Voice(c["t"], c["dur"], "comm", c["goal"])) for c in comm]
    if callouts:
        todo += [(c["t"], 2, (c, f)) for c, f in w["cues"]]
    todo.sort(key=lambda x: (x[0], x[1]))
    heard: list[list] = []  # [start, end, kind, priority]
    last_call, name_t, client_dropped = -99.0, -99.0, 0
    for t, _, x in todo:
        busy = heard[-1][1] if heard else float("-inf")
        if isinstance(x, Voice) and x.kind == "narration":
            start = max(t, busy)
        elif isinstance(x, Voice):
            if x.goal and busy > t:
                heard[-1][1], start = t, t  # a goal line cuts in
            elif busy - t > WAIT_S:
                client_dropped += 1
                continue
            else:
                start = max(t, busy)
        else:
            cue, frame = x
            c = callout_for(cue, frame, name_t)
            if not c:
                continue
            pri, clips, is_name = c
            calling = heard and heard[-1][2] == "call" and busy > t
            if (busy > t and not (calling and pri > heard[-1][3])) or (t - last_call < CALL_GAP_S and not (calling and pri > heard[-1][3])):
                continue
            if calling:
                heard[-1][1] = t
            last_call, name_t = t, (cue["t"] if is_name else name_t)
            heard.append([t, t + clips * CALL_CLIP_S + (0.25 if is_name else 0.0), "call", pri])
            continue
        heard.append([start, start + x.dur, x.kind, 99])
    return [(a, b) for a, b, *_ in heard if b > a], client_dropped


def coverage(spans: list[tuple[float, float]], t0: float, t1: float) -> tuple[float, float, float]:
    """(share of 30-s bins with speech, longest silence in s, share of time with speech)."""
    spans = sorted((max(a, t0), min(b, t1)) for a, b in spans if b > t0 and a < t1)
    bins = max(1, round((t1 - t0) / BIN_S))
    hit = {int((s - t0) // BIN_S) for a, b in spans for s in _range(a, b)}
    longest, edge, talk = 0.0, t0, 0.0
    for a, b in spans:
        longest = max(longest, a - edge)
        talk += max(0.0, b - max(a, edge))
        edge = max(edge, b)
    longest = max(longest, t1 - edge)
    return len({h for h in hit if h < bins}) / bins, longest, talk / (t1 - t0)


def _range(a: float, b: float) -> list[float]:
    out, s = [], a
    while s < b:
        out.append(s)
        s = (s // BIN_S + 1) * BIN_S
    return out


def q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


def label(w: dict) -> str:
    chapter = {0.0: "kickoff", 19.0: "first goal", 76.0: "late drama"}
    return f"seed {w['seed']} · {int(w['start'])}'" + (f" ({chapter[w['start']]})" if w["seed"] == 7 else "")


def report(ws: list[dict], model_name: str, minutes: float) -> list[str]:
    rows, cfg = [], {"narration only": [], "+ callouts": [], "+ callouts + commentator": []}
    lat = [x for w in ws for x in w["comm"]["latency"]]
    tot = {k: sum(w["comm"]["counts"][k] for w in ws) for k in ws[0]["comm"]["counts"]}
    played = client_dropped = 0
    mins = sum((w["t1"] - w["t0"]) / 60 for w in ws)
    for w in ws:
        a = coverage(playback(w, [], False)[0], w["t0"], w["t1"])
        b = coverage(playback(w, [], True)[0], w["t0"], w["t1"])
        spans, cd = playback(w, w["comm"]["lines"], True)
        c = coverage(spans, w["t0"], w["t1"])
        client_dropped += cd
        played += len(w["comm"]["lines"]) - cd
        for k, v in zip(cfg, (a, b, c), strict=True):
            cfg[k].append(v)
        rows.append(f"| {label(w)} | {a[0]:.0%} / {a[1]:.0f} s | {b[0]:.0%} / {b[1]:.0f} s | {c[0]:.0%} / {c[1]:.0f} s | "
                    f"{len(w['comm']['lines']) - cd} |")
    lines_sent = sum(len(w["comm"]["lines"]) for w in ws)
    out = [f"# Live commentary (generated by `python -m eval.commentary`, {datetime.date.today()})", "",
           f"Model `{model_name}`, commentary prompt v{COMMENTARY_PROMPT_VERSION}, English listener, Casual, {DELAY_S:.0f} s delay, "
           f"{len(ws)} windows of up to {minutes:.0f} minutes ({mins:.0f} match minutes): the three chapters of the demo seed 7 and "
           "seeds 11-15 (reporting seeds) from minute 19. Every commentator line is generated live (no cache).", "",
           "## Does the match talk?", "",
           "Share of 30-s windows with any speech / longest silence. Speech = narration, callouts or commentator lines (the ball "
           "sounds play throughout and are not counted).", "",
           "| window | narration only | + callouts | + callouts + commentator | commentator lines heard |", "|---|---|---|---|---|", *rows]
    tot_row = []
    for v in cfg.values():
        tot_row.append(f"{statistics.mean(x[0] for x in v):.0%} / {max(x[1] for x in v):.0f} s")
    out += [f"| **all** (mean / worst) | {' | '.join(tot_row)} | {played} |", ""]
    out += ["| | narration only | + callouts | + callouts + commentator |", "|---|---|---|---|",
            "| share of time with speech | " + " | ".join(f"{statistics.mean(x[2] for x in v):.0%}" for v in cfg.values()) + " |",
            "| median longest silence per window | "
            + " | ".join(f"{statistics.median(x[1] for x in v):.0f} s" for v in cfg.values()) + " |",
            "", "## Commentator", "",
            "| | |", "|---|---|",
            f"| segments commented (one model call each) | {tot['segments']} |",
            f"| segments skipped (backlog) | {tot['skipped']} |",
            f"| latency, model + Verifier + voice, p50 / p95 / max | {q(lat, 0.5):.2f} s / {q(lat, 0.95):.2f} s / "
            f"{max(lat, default=0):.2f} s |",
            f"| budget (delay - {LATE_MARGIN_S:.0f} s margin, from segment end) | {DELAY_S - LATE_MARGIN_S:.0f} s |",
            f"| calls over the budget (the stream gave up, silence) | {tot['timeouts']} |",
            f"| segments where the model chose silence | {tot['silent']} ({tot['silent'] / max(1, tot['segments']):.0%}) |",
            f"| lines sent (English) | {lines_sent} |",
            f"| lines heard / per match minute | {played} / {played / mins:.1f} |",
            f"| lines dropped by the Verifier (both languages failed) | {tot['dropped']} |",
            f"| lines failed in one language only: EN / TR | {tot['en_failed'] - tot['dropped']} / {tot['tr_failed'] - tot['dropped']} |",
            f"| lines dropped as late (server) | {tot['late']} |",
            f"| lines dropped because the voice was taken (client) | {client_dropped} |",
            f"| model or voice errors | {tot['errors']} |", ""]
    demo = next((w for w in ws if w["seed"] == 7 and w["start"] == 19.0), ws[0])
    out += [f"## Ten consecutive lines ({label(demo)}), verbatim", "", "| match time | style | EN | TR |", "|---|---|---|---|"]
    for line in demo["comm"]["lines"][:10]:
        mm, ss = divmod(int(line["t"]), 60)
        out.append(f"| {mm}:{ss:02d} | {line['style']} | {line['en']} | {line['tr'] or '(dropped)'} |")
    out += ["", "Method: the server's commentator stream on a simulated clock (one match second per wall second, as at speed 1) and the "
            "client's one-voice rules, simplified (see the module doc). Narration durations are estimated from the English template "
            "text, callouts at 0.55 s per clip; commentator durations come from the real clips. The Verifier checks names and "
            "numbers against the segment facts and a list of invented details; it does not check every adjective.", ""]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", nargs="*", help="seed:minute, e.g. 7:19 11:19 (default: seed 7 chapters + seeds 11-15 from 19')")
    ap.add_argument("--minutes", type=float, default=15.0)
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--samples", type=Path, help="write every line heard (JSON rows)")
    args = ap.parse_args()
    load_env()
    model = get_commentator()
    if model is None:
        raise SystemExit("No commentator: run with HTG_ENV=azure (and COMMENTARY not off).")
    from htg.speech.azure import AzureSpeech

    windows = [(int(s), float(m)) for s, m in (x.split(":") for x in args.windows)] if args.windows else WINDOWS
    with tempfile.TemporaryDirectory() as tmp:
        speech = AzureSpeech(cache_dir=Path(tmp))  # no clip cache: every voice call is live

        def one(win: tuple[int, float]) -> dict:
            w = collect(*win, args.minutes)
            w["comm"] = run_commentator(w["segs"], model, speech, known_names(w["meta"]))
            print(f"{label(w)}: {w['comm']['counts']['segments']} segments, {len(w['comm']['lines'])} lines", flush=True)
            return w

        with ThreadPoolExecutor(len(windows)) as pool:
            ws = list(pool.map(one, windows))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(report(ws, model.name, args.minutes)))
    if args.samples:
        with args.samples.open("w") as f:
            for w in ws:
                for line in w["comm"]["lines"]:
                    f.write(json.dumps({"seed": w["seed"], "start": w["start"], **line}, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
