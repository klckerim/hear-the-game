# Hear the Game

**Follow a football match with your eyes closed.**
Hear the Game turns a live stream of football events into spatial sound and short, verified narration, so blind and partially sighted fans (and anyone who can't look at a screen) can follow the shape of a match in real time, in their own language.

> Built for the Microsoft × Premier League **Inside the Game** hackathon (October 2026).
> Status: day 1 of 7. The data layer is done and validated. The audio and agent layers are in progress. A working sound prototype lives in [`prototype/`](prototype/).

## The problem

Live audio-described commentary for blind and partially sighted fans depends on trained human commentators. It is scarce, limited to a few languages, and in some stadiums it runs about 30 seconds behind the action. Most matches, most leagues and most languages get none.

## How it works

Two paths run at different speeds:

| Path | Latency | What it does | AI? |
|---|---|---|---|
| **Fast path: sound** | < 100 ms | Every 125 ms the ball becomes a short tone. **Pitch** encodes danger (an xT model), **left/right** encodes the flank as seen by the attacking team, **timbre** encodes which team has the ball, and a **heartbeat** encodes pressure on the ball carrier. | No. Deterministic, so it never waits for a model. |
| **Slow path: narration** | ~2 s | Detectors turn events into evidence-backed *insights*. An agent writes one sentence per insight, a verifier checks every number in it against the data, and a Director only lets it speak during dead balls or low-danger moments. | Yes. The LLM is used only for language. It never computes numbers. |

Pipeline: **Ingest** (event feed) → **Interpret** (state + detectors) → **Explain** (insights with evidence) → **Render** (sound cues, speech, overlay JSON) → **Personalize** (eyes-free / casual / analyst modes, favorite player, language).

## Data: synthetic, but calibrated on real football

The hackathon requires synthetic data. A synthetic match is only useful if it behaves like football, so the generator learns its statistics from real open data and is then checked against it.

```
real open data ──► htg.calibrate ──► calibration.json ──► htg.generate (seeded) ──► synthetic matches
  (data/raw, not                       (aggregates only,                            + hidden truth.json
   redistributed)                       committed)                                       │
                                                                     htg.validate ◄──────┘
```

* **Calibration sources**
  * [StatsBomb Open Data](https://github.com/hudl/open-data): 40 Premier League 2015/16 matches. Provides zone action probabilities, pass destinations, pass/carry lengths, pressure rates, xG by zone, an Expected Threat (xT) grid and action timing.
  * [SkillCorner Open Data](https://github.com/SkillCorner/opendata): A-League 2024/25 broadcast tracking (3 matches) and season physical aggregates. Provides ball speeds, possession durations and per-role running and sprint baselines.
* **Generator**: a seeded Markov process over a 12×8 grid. It outputs a raw event feed, a 10 Hz ball track and per-player, per-minute physical data. Teams and players are fictional.
* **Hidden scenarios (ground truth)**: every match contains four injected tactical stories, recorded in `truth.json` and never visible to the detectors. They are a pressing surge, a flank overload, a tempo drop and one player's fatigue. Because the truth is known, the system's explanations can be **scored**, not just demonstrated.

### Validation (30 synthetic matches vs. real data)

| Per match | Real | Synthetic |
|---|---|---|
| Passes | 982.6 | 879.2 |
| Carries | 609.0 | 546.5 |
| Shots | 25.4 | 26.3 |
| Goals | 2.65 | 2.5 |
| Ball in play | ~55–60 min | 57.8 min |

| Distribution | KS statistic |
|---|---|
| Pass length | 0.049 |
| Time between on-ball actions | 0.100 |
| Moving ball speed | 0.180 |
| Action location along the pitch | correlation 0.944 |

Every injected scenario changes the statistic a detector would watch. Median effect sizes are: pressure on the opponent **+81%**, passes to the overloaded flank **+98%**, time between actions **+68%**, high-speed running of the tired player **−60%**. The full report is in [`data/synthetic/validation.md`](data/synthetic/validation.md), with plots in `validation.png`.

**Known limitations**
* Ball speed matches less well (KS 0.18) because it is calibrated on A-League broadcast tracking while timing comes from Premier League event data.
* Two constants (`SHOT_SCALE`, `FINISH_SCALE`) were fitted by simulation, because the chain has no defensive shape and slightly over-visits the box.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
bash scripts/download_data.sh      # ~400 MB into data/raw (git-ignored)
python -m htg.calibrate            # -> data/calibration/calibration.json (reproducible byte-for-byte)
python -m htg.generate --seeds $(seq 1 30)   # the validation report uses seeds 1-30
python -m htg.validate             # -> data/synthetic/validation.md + .png
ruff check . && pytest
```

Calibration is already committed, so `htg.generate` works without downloading anything. Matches are deterministic per seed, so only seeds 1-3 are committed as samples; the rest regenerate byte-for-byte. Copy `.env.example` to `.env` once Azure resources exist (day 3 onward).

## Run it locally

```bash
python -m services.engine.run_local --seed 1 --speed 1 --start-minute 10   # streams to ws://localhost:8765
open web/live.html                                                         # then press "Dinlemeye başla" (audio needs a click)
```

The server waits for the first listener, then replays the match in real time. The browser makes all sound itself from the
state packets. By default narration is the deterministic template sentence (EN/TR) read by the browser's own voice.
`--mode eyes_free|casual|analyst` sets how often the Director may speak; `--speed 4` fast-forwards.

### Verified narration and Azure voices

```bash
pip install -e ".[azure]" && az login                  # fill .env from .env.example (Foundry + Speech endpoints)
HTG_ENV=azure python -m htg.narration.pregen --seed 7  # model writes EN+TR, Verifier checks, Azure voices MP3 -> data/cache/
HTG_ENV=azure python -m services.engine.run_local --seed 7 --start-minute 13   # plays cached clips; a cache miss gets 4 s, then falls back
HTG_ENV=azure python -m eval.narration --seeds 11-30 --limit 100              # writes eval/results/narration.md
```

The model only turns computed facts into one sentence per language; a plain-Python Verifier rejects any number, name, cause or
medical claim that is not in the facts, and a rejected sentence falls back to the template. The demo match (seed 7) is pre-generated and
committed under `data/cache/`, so the demo never waits for a model. The page shows "doğrulandı / verified" for model text and
"şablon / template" for the fallback.

## Repository layout

```
schemas/        event, insight and cue JSON schemas (the contracts between layers)
htg/            pitch geometry, calibrate, generate, validate
data/
  calibration/  aggregated statistics learned from real data (committed)
  synthetic/    generated matches: meta, events.jsonl, ball.parquet, physical.jsonl, truth.json
tests/          schema validity, determinism, realism bounds, truth not leaked into events
prototype/      day-0 sound prototype (offline renderer + browser Web Audio page)
scripts/        data download
.github/        CI: lint, tests, generator smoke test
```

## Roadmap

| Day | Deliverable |
|---|---|
| 1 ✅ | Schemas, calibration, generator, validation, tests |
| 2 | State engine, insight detectors, scored against `truth.json` |
| 3 | Microsoft Foundry narrator agent, verifier, Azure AI Speech (TR/EN) |
| 4 | Personal modes, favorite-player earcon, "what did I miss?" recap |
| 5 | Azure Container Apps deployment, latency measurement |
| 6 | Listening tests, documentation |
| 7 | Demo video and submission |

## Attribution

Calibration uses data provided by **StatsBomb** (Hudl) under the [StatsBomb Open Data terms](https://github.com/hudl/open-data). SkillCorner data is used under the MIT licence. No raw rows from either source are redistributed; only aggregated statistics in `data/calibration/` are published.

## License

Code is released under the [MIT License](LICENSE). Teams, players and matches are fictional and synthetic; no real club, player or league branding is used.
