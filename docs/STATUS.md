# Status (update at the end of every work session)

Last updated: 2026-10-24 (Day 5 closed: deployed and verified). Next: Day 6 (eval numbers into README, listening tests, diagram).

## One-line summary
Hear the Game: synthetic football events → spatial sound made on the device (Web Audio) + verified TR/EN narration
(Foundry + Azure AI Speech), for blind and low-vision fans. Deadline Oct 27.

## Done
- Day 0: sound prototype (`prototype/`) proves the idea.
- Day 1: schemas, calibration from real open data, seeded generator with hidden scenarios, validation, 8 tests, CI config.
- Day 2 PR 1 (branch `day2/state-engine`): `state.schema.json`, `htg/replay.py`, local adapters, `htg/engine/state.py`, 15 new tests. 
- Day 2 PR 2: `htg/engine/detectors.py` (pressure_shift, tempo_change, flank_overload, physical_drop, chance, goal), `htg/narration/templates.py` (EN/TR), `eval/scenarios.py`, 9 tests. Tuned on seeds 1-10 (two rounds); reported on 11-30 in `eval/results/scenarios.md`: recall press 85%, tempo 85%, flank 40%, fatigue 95%; precision 36% / 68% / 11% / 60%; median delay 264 / 283 / 336 / 589 s. Flank overload is weak: report honestly. Deviations from the task: tempo window 7 min and ratio 1.5, press ratio 1.7 and >=25 actions, flank ratio 2.0 and >=25 passes, fatigue window 8 min and ratio 0.5 (noise in per-minute running made the spec values fire far too often). 
- Day 2 PR 3: `htg/engine/director.py` (expired/goal/repeat/dangerous-ball/silence-budget rules, one speech at a time), `services/engine/run_local.py` (`LivePipeline` + WebSocket), `web/live.html` (jitter-buffered live client, `speechSynthesis` narration), 11 tests. Listened to live in the browser and approved by the owner (2026-10-21); CI green. Day 2 is closed.

## Day 3 progress
- PR 1 (Narrator, Verifier, cached service) and PR 2 code (`htg/speech/azure.py`, `htg/narration/pregen.py`) done. Demo seed: **7**, window from minute 13
  (1 goal + 5 non-chance Insights in 10 min; `python -m htg.narration.pregen --find-demo`, seeds 1-10 only).
- Demo cache for seed 7 generated with Azure (33 sentences x EN+TR, all first-pass `llm`, 2.4 MB) and committed (`3fb901c`). Owner listened to most clips.
- Known quality nits (not fixed): awkward chance/danger sentences ("17 - The Reds chance", "danger level 90"); voices are neutral (no SSML styles, deliberate cut).
  Optional small PR later: radio-tone prompt + faster/higher SSML for goals. If names need `ALIASES`, regenerate and drop stale clips from `data/cache/audio`.
- PR 3 done: `services/engine/resolve.py` (cache first, 4 s deadline, template fallback, stale non-goal speech dropped after 8 s), `speech` message now has
  `source`, `audio`, `duration_s`; `web/live.html` plays Azure clips on an un-ducked voice bus with "doğrulandı/verified" vs "şablon/template" tag;
  `eval/narration.py` -> `eval/results/narration.md` (100 Insights, seeds 11-30): first-pass Verifier 100% EN and TR, fallback 0%, mutation catch rate 100% (synthetic).
- **Finding:** model latency is p50 10.7 s / p95 17.4 s (gpt-5-mini, EN+TR in one call), TTS p50 0.4 s. A live cache miss therefore usually exceeds the 4 s deadline and
  falls back to template text; the demo relies on the pre-generated cache. Say so in the README; a faster non-reasoning model would fix it if live narration matters.
- Owner listened to Azure clips in the browser end-to-end (2026-10-22): works. Day 3 is closed and merged.
- TODO later: model latency (p50 10.7 s). Try a faster non-reasoning deployment or shorter prompt, re-run `eval.narration`, update README numbers.

## Day 4 (closed 2026-10-23;  task: `docs/tasks/2026-10-23-day4.md`)
- `web/live.html`: TR/EN app language (one `T` dictionary, also picks narration language), modes audio-only/casual/analyst (sent to the Director via `set_mode`),
  favourite-player chime, "what did I miss" panel. Server: `WebSocketBroadcaster(on_message=)`, `hello.teams[*].players`, `event_cue.player_id`. 2 new tests.
- Mobile layout fixed (TR/EN switch was off-screen). Owner tried it by ear, by eye and with a screen reader (VoiceOver): OK. This is a manual check, not blind-user validation; do not claim more in the README.
- Cut: visual polish beyond the above. Work now goes straight to `main` (no branches/PRs).

## Day 5 (code done 2026-10-24; task: `docs/tasks/2026-10-24-day5.md`)
- `services/engine/serve.py`: static client + `/healthz` + `/ws` on one port, one replay session per listener (max 20, 15 min of match time each), seed 7 from minute 13.
  `web/live.html` defaults to same-origin WebSocket. `Dockerfile` (generates match 7 at build), `azure.yaml`, `infra/` Bicep (compiles): Log Analytics, App Insights,
  ACR, Container Apps env + app (min 1 replica), user-assigned identity with AcrPull. 2 new tests. Docker image built and run locally: healthz + WebSocket OK.
- **Deployed** (`azd up`, env `htg-demo`, rg `rg-htg-demo`, swedencentral): https://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/
  Checked from outside: `/healthz` ok, WebSocket `hello` after 1.2 s, verified (`llm`) narration with audio from the cache. Roles on the `hearthegame` AIServices
  resource for the app identity: Cognitive Services User, Azure AI Developer, Cognitive Services OpenAI User ("Azure AI User" does not exist in this tenant).
  Owner ran a live Speech TTS call and a Foundry model call from inside the container: both OK, so cache misses can reach Foundry/Speech.
- Min replicas is 1 (`minReplicas` param); set it to 0 after judging to save cost. Latency numbers on the deployed URL are not measured yet (Day 6).
- Not done: App Insights is provisioned and its connection string is an env var, but the app sends no telemetry yet (Container Apps logs go to Log Analytics). Do not claim tracing in the README unless added.

## In progress
- Local setup (venv with Python 3.11+, GitHub push). `microsoft-learn` MCP via `.mcp.json`; Azure MCP intentionally skipped.

## Plan (simplified, 2026-10-21)
| Day | Date | Deliverable |
|---|---|---|
| 2 | Oct 21 | Replay, state engine, detectors scored vs truth, Director, live sound page (see `docs/tasks/`) |
| 3 | Oct 22 | Foundry narrator + Verifier (fallback to templates), Azure TTS TR/EN, clip cache; pre-generate demo match narration |
| 4 | Oct 23 | UI day: good-looking single-page client (vanilla JS), modes (eyes-free / casual / analyst), favorite-player earcon, simple "what did I miss", app language TR/EN (all UI strings in one dictionary, browser language as default, one selector for both UI and narration) |
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
- Live narration on a cache miss usually exceeds the 4 s deadline (model p50 10.7 s); the demo depends on the pre-generated cache. State this in the README.
- Keep the deployed demo cheap: single container app; scale-to-zero is not ideal for a live demo, so use min 1 replica only during judging.
- iOS Safari background audio untested.
- No claim of blind-user validation unless it actually happens.
- Detector scores may be mediocre on some scenario types; report honestly.

## Working method
- Claude Code (VS Code) writes code; GitHub is the source of truth; one task per session, `/clear` between PRs.
- Chat (claude.ai) is for architecture, briefs, review and unblocking. Reply language: Turkish, direct, practical.
