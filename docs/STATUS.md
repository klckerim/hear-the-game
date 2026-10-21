# Status (update at the end of every work session)

Last updated: 2026-10-21 (before Day 2).

## One-line summary
Hear the Game: synthetic football events → spatial sound made on the device (Web Audio) + verified TR/EN narration
(Foundry + Azure AI Speech), for blind and low-vision fans. Deadline Oct 27.

## Done
- Day 0: sound prototype (`prototype/`) proves the idea.
- Day 1: schemas, calibration from real open data, seeded generator with hidden scenarios, validation, 8 tests, CI config.
- Day 2 PR 1 (branch `day2/state-engine`): `state.schema.json`, `htg/replay.py`, local adapters, `htg/engine/state.py`, 15 new tests. 
- Day 2 PR 2: `htg/engine/detectors.py` (pressure_shift, tempo_change, flank_overload, physical_drop, chance, goal), `htg/narration/templates.py` (EN/TR), `eval/scenarios.py`, 9 tests. Tuned on seeds 1-10 (two rounds); reported on 11-30 in `eval/results/scenarios.md`: recall press 85%, tempo 85%, flank 40%, fatigue 95%; precision 36% / 68% / 11% / 60%; median delay 264 / 283 / 336 / 589 s. Flank overload is weak: report honestly. Deviations from the task: tempo window 7 min and ratio 1.5, press ratio 1.7 and >=25 actions, flank ratio 2.0 and >=25 passes, fatigue window 8 min and ratio 0.5 (noise in per-minute running made the spec values fire far too often). 
- Day 2 PR 3: `htg/engine/director.py` (expired/goal/repeat/dangerous-ball/silence-budget rules, one speech at a time), `services/engine/run_local.py` (`LivePipeline` + WebSocket), `web/live.html` (jitter-buffered live client, `speechSynthesis` narration), 11 tests. Sound check by ear in a browser is still the owner's step.

## In progress
- Local setup (venv with Python 3.11+, GitHub push). `microsoft-learn` MCP via `.mcp.json`; Azure MCP intentionally skipped.

## Plan (simplified, 2026-10-21)
| Day | Date | Deliverable |
|---|---|---|
| 2 | Oct 21 | Replay, state engine, detectors scored vs truth, Director, live sound page (see `docs/tasks/`) |
| 3 | Oct 22 | Foundry narrator + Verifier (fallback to templates), Azure TTS TR/EN, clip cache; pre-generate demo match narration |
| 4 | Oct 23 | UI day: good-looking single-page client (vanilla JS), modes (eyes-free / casual / analyst), favorite-player earcon, simple "what did I miss" |
| 5 | Oct 24 | Deploy: one Container App (engine + static client), Speech + Foundry, App Insights, azd/Bicep; measure latency |
| 6 | Oct 25 | Eval numbers into README, 1-2 listening tests, docs, architecture diagram |
| 7 | Oct 26 | Demo video, buffer fixes |
| - | Oct 27 | Submit in the morning, leave the evening as slack |

## Decisions
- Idea: Hear the Game (not PitchSynth).
- Numbers from code, words from LLM; Verifier + template fallback; sound never waits for LLM.
- Demo narration is pre-generated and cached, so the demo never depends on live model latency.
- No Event Hubs / Cosmos / Web PubSub / Vite client / complex agent orchestration. Described as production path only.
- Python 3.11+, vanilla JS client, local-first adapters (`EventSource`, `Broadcaster`, `Speech`).
- Repo is public MIT. Fictional teams/players only.

## Risks
- Keep the deployed demo cheap: single container app; scale-to-zero is not ideal for a live demo, so use min 1 replica only during judging.
- iOS Safari background audio untested.
- No claim of blind-user validation unless it actually happens.
- Detector scores may be mediocre on some scenario types; report honestly.

## Working method
- Claude Code (VS Code) writes code; GitHub is the source of truth; one task per session, `/clear` between PRs.
- Chat (claude.ai) is for architecture, briefs, review and unblocking. Reply language: Turkish, direct, practical.
