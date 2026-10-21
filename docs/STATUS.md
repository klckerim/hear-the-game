# Status (update at the end of every work session)

Last updated: 2026-10-21 evening (Day 6 in progress: steps 0-4, 6, 7 done; README next). Calendar note: the plan's dates (Day 5 = Oct 24)
run ahead of the real calendar; everything up to Day 6 was actually done on 2026-10-21, which is the date in the results files.

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
- (Latency TODO resolved on Day 6: reasoning effort `minimal` + prompt v3, p50 1.54 s / p95 2.89 s.)

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
- Telemetry code was added after this (see Pre-Day-6 fixes); do not claim tracing in the README until a trace is seen in App Insights.

## Pre-Day-6 fixes (2026-10-24, three commits)
- **Latency:** `FOUNDRY_REASONING_EFFORT` (default `minimal`, set in `.env.example`, Bicep param and container env) is passed to `chat.completions.create` only when set.
  Not part of the fingerprint; a test checks the seed-7 demo cache still hits. `eval.narration` already used a temp cache; it now has `--out`.
  Measured (HTG_ENV=azure, seeds 11-30, 30 Insights, gpt-5-mini, minimal): narration p50 **1.87 s** / p95 4.90 s (was 10.7 / 17.4), first-pass Verifier 93% EN and TR
  (was 100% on 100 Insights; small sample), fallback 0%, TTS p50 0.53 s / p95 2.28 s. Result is in the scratchpad, **`eval/results/narration.md` is not overwritten yet** (Day 6: rerun with `--limit 100`).
  p50 is under the 4 s deadline, but p95 is not: a few live cache misses still fall back to the template.
- **warm_up** runs in `asyncio.to_thread` (serve and run_local); test shows the loop keeps ticking during a slow warm-up.
- **Telemetry:** `htg/telemetry.py` (`setup()` only with `APPLICATIONINSIGHTS_CONNECTION_STRING`; Azure Monitor + OpenAI instrumentation, errors never stop the server).
  Metrics `htg.sessions.active`, `htg.speech.resolved` (source cache|llm|template, lang), `htg.speech.resolve_ms`, `htg.speech.dropped_stale`; span `htg.narrate_insight`
  (insight.type, cached, verifier.attempts, verifier.reasons, source.en/tr). `narrate_insight` result has a `cached` flag (not stored in the cache files).
  Message content capture is on in the container (synthetic facts only). `opentelemetry-api` is a core dependency (no-op); exporters are in the `[azure]` extra.
  Pins: `opentelemetry-util-genai==1.1b0` and `httpx` (openai-v2 2.4b0 breaks with util-genai 1.2b0 and imports httpx, while openai 3.x ships httpx2).
  **Verified in Azure (owner, after `azd deploy`):** `htg.narrate_insight` spans arrive in App Insights `appi-tv2ah3k7jdu46`, including one `cached=false`
  (live Foundry call; Analyst mode, minute 21:42 chance is not in the demo cache). Foundry project `hearthegame` is connected to it (Tracing, project managed identity).
  Prompt/response content was **not** seen yet: on the legacy path it goes out as `gen_ai.*` log events. Optional fix: `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`
  + `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only` puts it on the span. README may claim tracing of narration + Verifier, not of message content.
- **Mobile/desktop layout:** TR/EN switch no longer moves the page (fixed caption height, one-line scorebar, title + switch on one row on phones, reserved text heights).
  Checked with headless Chrome screenshots at 1280/375/360/320 px, not on a real phone.

## Day 6 (in progress; task: `docs/tasks/2026-10-25-day6.md`)
- **Category: Best Use of Microsoft Foundry** (owner, 2026-10-21). Not "multi-agent": the code is one Foundry call per Insight + deterministic
  Verifier, detectors and Director. README framing follows this.
- **Quality pass (owner said yes):** prompt v3 (radio tone, <= 20 words, fact meanings, one hand-written EN/TR example per Insight kind with
  fixture teams Greens/Whites), `recent_min` replaces `window_min` (`*_now` = last N min, `*_before` = earlier in the match; schema description
  updated), no match minute and no danger value in claim_facts, goal facts without the opponent's name. Verifier: Turkish `42%`/`%42`,
  jargon (window, danger level, pencere, tehlike seviyesi), code values (`off_target`), max 25 words. Director drops danger-only chances
  (the sound carries danger; held until the ball was quiet they were stale). Goal SSML: rate +10%, pitch +6%.
  Seed-7 cache regenerated (31 spoken Insights, all first-pass `llm`, 2.0 MB audio, stale clips deleted). **Owner still has to listen to 10 clips
  per language.** Text to watch: "Arda levels it" (79'), "puts the Blues ahead but the score is 1-2" (87'): inferred from the score, correct.
- **Found by reading samples, not by the Verifier:** prompt 2 read out `off_target` in 13 of 200 sentences, invented shot locations, and one
  demo goal credited the score to the wrong team ("0-1 Kırmızılar lehine"). Fixed as above; documented in `eval/results/narration.md`.
- Step 1 `eval/results/narration.md` (+ `narration_samples.jsonl`, `narration_samples_prompt2.jsonl`): prompt 3, minimal, 100 Insights:
  narration p50 1.54 s / p95 2.89 s, first pass 100% EN and TR, fallback 0%, **0 real Verifier rejections** (reported as 0, not invented).
  Dated history table: v1 default 10.73/17.42 s, v1 minimal (30) 1.87/4.90 s, v2 default 7.71/17.51 s, v2 minimal 1.58/2.79 s.
  Local `.env` has no `FOUNDRY_REASONING_EFFORT` (owner to add `minimal`); the container sets it.
- Step 2 `eval/latency.py` -> `eval/results/latency.md` (Istanbul -> Sweden Central): 1 session hello 1.5 s, state 200/214 ms, speech 100% `llm`
  with audio. **10 sessions: hello ~13 s and a 15.8 s stall** (each listener ran its own warm-up on the shared CPU). Fixed: warm up once per
  server, deep-copy per session (`serve.warmed`), resolver built off the loop; local 10-session hello p50 2218 -> 597 ms.
  **Needs `azd up` and a re-measure on the deployed app.** `htg.speech.dropped_stale` count from the portal: not read yet.
- Step 3 `eval/foundry_eval.py` -> `eval/results/foundry_eval.md`: Foundry Evals API (builtin groundedness + fluency, judge gpt-5-mini,
  100 Insights x EN/TR). Groundedness 4.99 / 4.99; fluency 3.13 EN / 3.48 TR (136 of 139 reasons for a 3 cite brevity). Portal link in the file.
- Step 4 (Bicep): `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` + `CAPTURE_MESSAGE_CONTENT=span_only`; verified locally that
  `gen_ai.input.messages` / `gen_ai.output.messages` land on the chat span. **Not yet seen in App Insights** (needs `azd up`, then owner checks).
- Step 6 `docs/listening-test.md`: protocol, questions TR/EN, answer key for minutes 13-23 from the match data. 10 minutes, not 5 (the goal is
  at 22:36). **Not run yet.**
- Step 7: `docs/design.md` carries the "original design" note; this STATUS cleaned up.
- Left: `azd up` + re-measure 10 sessions; owner trace check + screenshots; README rewrite (step 5); listening test (owner).

## Day 7 needs (video)
- Screenshots in `docs/img/`: one App Insights trace (htg.narrate_insight with verifier.* attributes + chat span with prompt/output),
  the Foundry evaluation run, the App Insights metrics chart (htg.speech.resolved by source).
- Demo minute: seed 7 from minute 13; the goal (Baptiste, Blues) comes at 22:36, about 9.5 minutes in. For a short video, either cut, or
  start the server at a later minute (would need a new pregen window check).
- Numbers to show: detector recall/precision (seeds 11-30, flank precision 11% stated), narration p50 1.54 s / p95 2.89 s (was 10.7 / 17.4),
  Verifier first pass 100% with 0 real rejections plus the samples finding, groundedness 4.99, deployed latency after the fix.

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
- Hackathon category: **Best Use of Microsoft Foundry** (2026-10-21).
- Danger-only chances are not spoken (the sound carries danger); shots, goals and tactical Insights are.

## Risks
- Live narration on a cache miss: p50 1.54 s / p95 2.89 s (prompt 3, minimal effort, offline eval), so most misses now make the 4 s deadline;
  the slowest still fall back to the template, and deployed misses also pay TTS (p50 ~0.45 s). The demo still uses the pre-generated cache.
- Many listeners joining at once stalled the server before the warm-up fix; re-measure after `azd up` before judging.
- The Verifier checks numbers, names, jargon and code values; it cannot catch invented details without a number or a name. Say so in the README.
- Keep the deployed demo cheap: single container app; scale-to-zero is not ideal for a live demo, so use min 1 replica only during judging.
- iOS Safari background audio untested.
- No claim of blind-user validation unless it actually happens.
- Detector scores may be mediocre on some scenario types; report honestly.

## Working method
- Claude Code (VS Code) writes code; GitHub is the source of truth; one task per session, `/clear` between PRs.
- Chat (claude.ai) is for architecture, briefs, review and unblocking. Reply language: Turkish, direct, practical.
