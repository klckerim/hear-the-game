# Data: synthetic, but calibrated on real football

The hackathon requires synthetic data. A synthetic match is only useful if it behaves like football, so the generator learns
its statistics from real open data and is then checked against it. At runtime only synthetic matches are used.

```
real open data ──► htg.calibrate ──► calibration.json ──► htg.generate (seeded) ──► synthetic matches
  (data/raw, not                       (aggregates only,                            + hidden truth.json
   redistributed)                       committed)                                       │
                                                                     htg.validate ◄──────┘
```

## Calibration sources

- [StatsBomb Open Data](https://github.com/hudl/open-data): 40 Premier League 2015/16 matches. Zone action probabilities, pass
  destinations, pass and carry lengths, pressure rates, xG by zone, an Expected Threat (xT) grid and action timing.
- [SkillCorner Open Data](https://github.com/SkillCorner/opendata): A-League 2024/25 broadcast tracking (3 matches) and season
  physical aggregates. Ball speeds, possession durations, per-role running and sprint baselines.

Only aggregates are committed (`data/calibration/`); raw rows stay in the git-ignored `data/raw/`.

## Generator

A seeded Markov process over a 12×8 grid. It writes a raw event feed (`events.jsonl`), a 10 Hz ball track (`ball.parquet`) and
per-player, per-minute physical data (`physical.jsonl`). Teams and players are fictional. Same seed, same bytes.

**Hidden scenarios (ground truth).** Every match contains four injected tactical stories, recorded in `truth.json` and never read
by the detectors, the engine or the narrator (only `eval/` reads it): a pressing surge, a flank overload, a tempo drop and one
player's fatigue. Because the truth is known, the detectors are scored, not just demonstrated
([`eval/results/scenarios.md`](../eval/results/scenarios.md)). Thresholds were tuned on seeds 1-10 and are reported on seeds 11-30.

## Validation (30 synthetic matches vs. real data)

Full report: [`data/synthetic/validation.md`](../data/synthetic/validation.md), plots in `validation.png`.

| Per match | Real | Synthetic |
|---|---|---|
| Passes | 982.6 | 879.2 |
| Carries | 609.0 | 546.5 |
| Shots | 25.4 | 26.3 |
| Goals | 2.6 | 2.5 |

| Distribution | Real median | Synthetic median | KS |
|---|---|---|---|
| Pass length (m) | 15.14 | 16.13 | 0.049 |
| Time between on-ball actions (s) | 1.40 | 1.61 | 0.100 |
| Moving ball speed (m/s) | 5.86 | 6.83 | 0.180 |

Action location along the pitch (12 bands): correlation 0.944 between real and synthetic.

Every injected scenario changes the statistic a detector watches. Median change by scenario type: pressure on the opponent
**+81%**, passes to the overloaded flank **+98%**, time between actions **+68%**, high-speed running of the tired player **-60%**.

## Known limitations

- Ball speed matches less well (KS 0.18): it is calibrated on A-League broadcast tracking, while timing comes from Premier League
  event data.
- Two constants (`SHOT_SCALE`, `FINISH_SCALE`) were fitted by simulation, because the chain has no defensive shape and slightly
  over-visits the box.

## Reproduce

```bash
bash scripts/download_data.sh      # ~400 MB into data/raw (git-ignored); only needed to recalibrate
python -m htg.calibrate            # -> data/calibration/calibration.json (byte-for-byte reproducible)
python -m htg.generate --seeds $(seq 1 30)
python -m htg.validate             # -> data/synthetic/validation.md + .png
```

Calibration is committed, so `htg.generate` works without downloading anything.

## Attribution

<img src="img/statsbomb-logo.png" alt="StatsBomb" height="40">

Data provided by **StatsBomb** (Hudl). Calibration uses StatsBomb Open Data under the
[StatsBomb Open Data terms](https://github.com/hudl/open-data), which ask users to credit StatsBomb as the source and show its logo
(from the StatsBomb Media Pack). Only aggregates derived from it are committed; no raw rows are redistributed.

Tracking and physical aggregates come from [SkillCorner Open Data](https://github.com/SkillCorner/opendata), used under the MIT
licence. No raw rows are redistributed.
