# Status (update at the end of every work session)

Last updated: 2026-10-22 night (Features C closed: evidence timeline + Analyst stats deployed and checked; screenshots open). Features B closed (deployed, recap and tour checked by the owner). Next: Day 7 video (owner brings the brief). Calendar note: the plan's dates (Day 5 = Oct 24)
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
- **Deployed** (`azd up`, env `htg-demo`, rg `rg-htg-demo`, swedencentral; app `ca-engine`, URL from `azd show` or the portal)
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

## Day 6 (closed 2026-10-22; task: `docs/tasks/2026-10-25-day6.md`)
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
- Step 7: STATUS cleaned up. (The Turkish design document was deleted on 2026-10-22: rule 4.9 wants submission material in English.)
- After listening (owner): Turkish voice spelled out number suffixes ("36'ydı") and read "yüzde 23." as an ordinal. Prompt 4 + Verifier
  rule (no suffix on numbers in Turkish); SSML says Turkish integers from words (`<sub alias>`; say-as cardinal is not supported for tr-TR),
  `SSML_VERSION` in the clip cache key. Cache regenerated. Narration re-measured with prompt 4: p50 1.58 s / p95 3.60 s, 100% first pass,
  0 rejections. Foundry eval kept on prompt-3 sentences (`narration_samples_prompt3.jsonl`), stated in the file and README.
- `azd up` done (warm-up fix + trace content). 10 sessions re-measured: hello p50 12.9 -> 3.8 s, longest state gap 15.8 -> 3.4 s. CPU stays 0.5.
- Step 5: README rewritten for the jury (216 lines, Mermaid diagram, every number checked against a file; sound mappings checked against
  `web/live.html`); long data detail moved to `docs/data.md`.
- **Owner, still open:** trace check in App Insights (content on the chat span) and screenshots `docs/img/trace.png`, `foundry-eval.png`,
  `metrics.png` (README does not embed them yet: add when the files exist); `htg.speech.dropped_stale` count (both deferred to a later session);
  listening test (README says not run). If the trace content shows, README may drop "configured" from the tracing row.

## Features A (2026-10-22 evening; task: `docs/tasks/2026-10-22-features-a.md`)
- Compliance: Turkish `docs/design.md` deleted (rule 4.9: English only); `docs/data.md` credits StatsBomb with the logo
  (`docs/img/statsbomb-logo.png`, added by the owner from the Media Pack). README section
  "Overlay feed (machine-readable)" with real seed-7 `insight` + `speech` messages; no integration claimed.
- Clubs: **Northport** (HOME, red) and **Valemont** (AWAY, blue), same in EN and TR (web search: no professional club by either name).
  Seeds 1-3 and 7 regenerated: `events.jsonl`, `ball.parquet`, `physical.jsonl`, `truth.json` byte-identical, only `meta.json`
  changed; a test pins the seed-1 events hash. Local seeds 4-30 regenerated too (git-ignored). Template EN possessive fixed
  ("Valemont's"). Historical results files keep the old names.
- Favourite club (client, `localStorage`): goal for = brighter, longer crowd swell; against = short muted crowd, no fanfare;
  "your team" text in the score bar and as a caption tag; `set_favourite` -> Director +1 priority (`decide(favourite=)`, tested).
  Narration text stays neutral (no cache multiplication).
- Personas: `persona_for(mode)` = analyst for Analyst, fan otherwise; in the `speech` message, the fingerprint and the prompt
  (`PROMPT_VERSION = 5`, one persona block each, fan/analyst EN+TR example per Insight kind). Verifier unchanged.
  `eval.narration --persona`: fan vs analyst numbers in `eval/results/narration.md` (fan 0.30 numbers per EN sentence vs 1.08).
  **Found:** colour-named fixture teams ("the Whites are feeling it") tripped Azure's content filter on 3/50 fan prompts; fixture
  is now Eastbrook/Westmere. Fan drafts exaggerated; fan block tightened. Invented colour without numbers/names remains possible.
- Chapters (`serve.CHAPTERS`, checked against events: goals 22:38, 79:11, 87:14): kickoff 0', first_goal 19' (default), late 76'.
  `/ws?chapter=`, unknown -> default; all three warmed at start; `hello` carries `score` and `seed` (test: late starts 0-1).
  `--start-minute` / `HTG_START_MINUTE` removed from `serve` (run_local keeps it).
- Small: Space starts/stops (not in select/input), "Space" hint by the button; status text "Demo match · seed 7".
- Pregen (all chapters x modes x favourite clubs): 36 (chapter, persona, Insight) rows, 34 narrations, 68 clips, **2.3 MB**, all
  first-pass `llm`; 26 stale narration files and 58 stale clips deleted. 3 sentences regenerated after reading (see narration.md).
  All sentences: `eval/results/demo_sentences.md`.
- Deployed by the owner with `azd deploy` (2026-10-22). Chapter minutes stay 0' / 19' / 76' (owner decided; 21' / 77' would
  cut the wait for the first goal from 3:38 to 1:38 and still keep one narration before it, if it matters for the video).
- **Owner, open:** read `demo_sentences.md`, listen to 5 clips per persona and language, check how the Turkish voice says
  "Northport" and "Valemont" (add `ALIASES` in `htg/speech/azure.py` if needed, then regenerate); check the deployed
  demo. Listening test protocol now runs locally from minute 13 (`docs/listening-test.md`).

## Features B (2026-10-22 night; task: `docs/tasks/done/2026-10-23-features-b.md`)
- **Recap agent built on Foundry Agent Service** (not the fallback loop): a prompt agent `htg-recap` with 4 function tools, created
  once per `RECAP_VERSION` (found again by its metadata), run with the Responses API (`azure-ai-projects` 2.x, added to the
  `[azure]` extra). API checked with the microsoft-learn MCP first; a spike worked in ~2 s per turn. Agent versions 1-6 exist in the
  Foundry project (6 is current; older ones are harmless).
- `htg/recap/tools.py`: `get_score`, `get_stats`, `get_insights`, `get_player` over a `MatchRecord` (events, physical rows, in-play
  ball frames, Insights detected once; detectors are causal so filtering by `t` equals running up to `t`). A `to_min` at the current
  minute means "now" (found by reading: the agent asked "60 to 70" at 70:38 and missed a shot).
- `htg/recap/agent.py`: tool loop (max 4 calls, max 6 turns), Verifier per sentence with the tool results as facts, **one revision
  turn** with the Verifier's reasons, template recap per language if no sentence survives, `htg.recap` span. Fake-model tests
  (`tests/test_recap.py`, 7): no leak after `t`, determinism, template passes the Verifier, loop stops at 4, wrong number dropped,
  template on failure, `recap_request` over the WebSocket.
- Verifier (shared with narration): Turkish suffixes also without an apostrophe ("87de") or written apart ("dakika 87 de", "3 ü").
  The 34 cached narration sentences still pass.
- Server: `recap_request` -> `recap` message (default the last 10 minutes, 25 s deadline, then template); at `period_end` of period 2
  the server sends a full-time `recap`. Only full-time recaps are cached: `data/cache/recap/*.json` + clips in `data/cache/recap/audio/`
  (kept apart from `data/cache/audio`, which the narration pregen prunes). `HTG_ENV=azure python -m htg.recap.pregen --seed 7`:
  6 recaps (club none/HOME/AWAY x fan/analyst), all `agent`, 1.2 MB. Text: `eval/results/recap_fulltime.md`.
- Client: "Catch me up" button shows "Preparing…", plays the recap like a narration (ducking, `Recap · verified` tag) and shows it
  above the narration list; no server answer in 30 s or not connected -> old behaviour (score + last 3 narrations).
- **Sound tour:** "New here? 60-second sound tour" under Start listening, 10 steps from `web/tour.json` (one table for captions and
  clips), real sound functions, caption in the existing `aria-live` caption box, `localStorage` `htg.tour` after done or skip,
  Skip (or Start listening) stops at once and starts nothing. Clips: `python -m htg.speech.tour` -> `data/cache/tour/` (20 clips,
  443 KB; voice ~35 s EN / ~40 s TR, plus ~20 s of demo sound). Served by `serve` at `/tour/...`; opened as a file there is no tour.
- Checked in headless Chrome via CDP (no console errors): tour steps advance (~5.5 s each), Skip ends it and marks it done; "Catch me
  up" locally gives a template recap; `late` chapter at 30x gets the full-time recap. Azure end to end at 30x: live recap 12.2 s
  including TTS (`agent` EN + TR, audio), full-time recap from the cache with audio.
- `eval/recap.py` -> `eval/results/recap.md` (seeds 11-30, n 20, prompt v6): Verifier first draft EN 95% / TR 83%, after revision
  98% / 88%, template fallback 0%, tool calls mean 2.0 (max 2), latency p50 6.06 s / p95 13.08 s (no TTS). History table and reading
  notes in the file (invented stats in tool *arguments* once, an unmeasured "more of the play", Turkish wording nits).
  Prompt tuned on seeds 1-10 (v6: 100% / 100% there). README: "Recap agent" section, stack row, Mermaid node, `recap` in the feed.
- Tour wording fixed after the owner listened: club-neutral ("home team / away team", "ev sahibi / deplasman") and the goal step
  describes the crowd and fanfare instead of "bright/short"; only `teams_*` and `goal_*` clips regenerated (`--only`).
- **Deployed and checked by the owner (2026-10-22):** `azd deploy` done; "Catch me up" tried many times on the deployed app and
  works; current `htg.recap` spans seen in App Insights (README updated). Nested model-call spans under it were not reported: do
  not claim them.
- Owner listened to the tour in TR and EN (2026-10-22). `half_time` chapter: **no** (owner decided).
- Full time was invisible (last ball frame 89:59.9, `period_end` never sent): `period_end` is now an `event_cue` with `period`;
  half-time two short whistles, full time two short + one long, clock "90:00 · MS/FT". Deployed by the owner. No added time in the
  synthetic data; adding it would change the generator and every measured number, so not done.
- A session stops after 15 match-minutes (`END_AFTER_S`; "First goal" ends at 33:59) with no notice to the listener. Owner: keep it
  for now. Possible small fix later: a `session_end` message and a caption "demo chapter ended, pick another".
- Owner listened to the full-time recap (2026-10-22). Features B is closed. (To hear it again locally:
  `HTG_ENV=azure python -m services.engine.serve --speed 10`, pick club and mode, chapter Late drama; it plays at 90:00.)

## Language split (2026-10-22; task: `docs/tasks/done/2026-10-23-language-split.md`)
- Client only (`web/live.html`; `speech`/`recap` messages and `tour.json` already carry EN + TR, so no `set_lang`). Interface language
  (header, `htg.lang`, browser default) drives the `T` dictionary; commentary language (next to the listening mode, `htg.commentary`,
  follows the interface until changed) drives narration, recaps, tour voice and the device voice. EN listed first.
- Dual caption when they differ (spoken sentence + muted interface-language line, each with its own `lang` attribute for screen
  readers); also under the agent recap in the "What did I miss?" panel. Caption box is one line taller (4 desktop / 6 phone) so the
  layout stays fixed. Changing either mid-match takes effect from the next sentence (clips decoded per language on demand).
- Checked in headless Chrome via CDP (local serve, 30x): EN page + TR commentary and the reverse, both stored and restored after reload,
  no console errors; screenshots at 1280 and 375 px. Deployed by the owner, who listened to EN page + TR commentary and the reverse
  (2026-10-22): closed.

## Features C (2026-10-22; task: `docs/tasks/done/2026-10-24-features-c.md`)
- **Evidence timeline** (Casual + Analyst, hidden in Audio only): strip for the session window under the pitch (`hello.window`; run_local
  falls back to first packet + 15 min). Markers are buttons: goal (large ringed dot), shot (small dot), Insight (diamond, filled once
  spoken), club colour; new Insights flash. Chance/goal Insights attach to their shot/goal marker (by evidence seq); danger-only chances
  are left out. Selecting one: evidence dots on the pitch for 6 s (fade), flank band for flank overloads, shot position + line to goal;
  "Why?" card (sentence by caption rules, verified/template/not spoken tag, `claim_facts` as key/value, evidence count).
- Server: `insight` message gains `text` (template EN/TR, for unspoken Insights), `evidence_points` (max 30; detector evidence is
  already <= 10) and `zone`; `event_cue` gains `x, y` for shots and goals (goal = the scoring shot's position), `speed_mps`, `outcome`,
  `length_m` for passes. Flank overload points are the pass **ends** (what the detector counted), others the start.
- **Deviation:** no pressure zone. On seeds 1-10, 223 of 338 pressed actions were in the pressed team's attacking half and 115 in its
  own, so the "pressed team's half" shade contradicted its own dots. Pressure shows dots only.
- **Analyst panel:** `stats` message every 10 s of match time from `htg/recap/tools.get_stats` (match / last 10 min), `serve` only
  (not run_local). Table with bars and a Match / Last 10 min toggle. Log: "Shot · Arda · 72 km/h · blocked", goals with scorer, passes
  > 30 m with length. Warmed-pipeline copy is now ~8 ms (was ~1 ms) because of the evidence position map.
- Tests: evidence points match events by seq and stay on the pitch, cap 30, flank zone frame, shot/goal cue positions, stats cadence
  and equality with `get_stats`. 80 tests pass. Checked in headless Chrome at 1280 and 375 px (casual, analyst, TR UI), no console errors.
- **MCP (part 3): dropped** by the owner after the deploy (2026-10-22); the live commentator matters more for the video. Fact keys in the Why card are the raw `claim_facts` names in both
  languages (e.g. "share now pct").
- Timeline window ends at full time (`meta.duration_s`): Late drama shows 76'-90', not 91'. Two layout tries (Why card above the
  caption with a height-capped pitch; Analyst panels moved up) were reverted at the owner's request.
- **Deployed** by the owner (`azd deploy`, 2026-10-22); timeline and Why card checked on the deployed app by the owner. Features C
  is closed. **Owner, open:** screenshots `docs/img/timeline.png`, `docs/img/analyst.png` later (README has a placeholder comment).

- Screenshots in `docs/img/`: one App Insights trace (htg.narrate_insight with verifier.* attributes + chat span with prompt/output),
  the Foundry evaluation run, the App Insights metrics chart (htg.speech.resolved by source).
- Demo start: chapters (0', 19', 76'). First goal (Baptiste, Valemont) at 22:38, 3.6 minutes into the default chapter; Late drama
  has two goals (79', 87').
- Numbers to show: detector recall/precision (seeds 11-30, flank precision 11% stated), narration p50 1.58 s / p95 3.60 s (was 10.7 / 17.4),
  Verifier first pass 100% with 0 real rejections plus the samples finding, groundedness 4.99, deployed latency after the fix.

## Extra: live commentary (2026-10-23; task: `docs/tasks/2026-10-24-extra-live-commentary.md`)
- **Voices (step 0), owner, 2026-10-23:** `en-US-Ethan:MAI-Voice-2.1-Flash` and `tr-TR-Aydın:MAI-Voice-2-Flash` work on our Speech
  resource (Foundry TTS playground). Every style in the task table sounded right: EN `excited`, `shouting`, `surprised`, `joyful`,
  `neutral`; TR `excited`, `serious`, `curious`, `neutral`. No mispronounced names (the test lines and squad names, EN and TR), so
  `ALIASES` in `htg/speech/azure.py` stays empty.
- **Part 1, callouts (done, 2026-10-23):** `htg/speech/callouts.py` pre-generates 148 clips (13 words + 2 clubs + 22 surnames, EN/TR,
  normal = `neutral` / excited = `excited`) with the commentary voice into `data/cache/callouts/` (1.25 MB, 1,048 TTS characters,
  0 fallbacks) plus `callouts.json`; served at `/callouts/...`. `AzureSpeech.commentate()` uses `SPEECH_VOICE_COMMENTARY_*` with
  `mstts:express-as`, retries once with `SPEECH_VOICE_COMMENTARY_FALLBACK_*` (style kept only where the voice has it), counts
  `htg.speech.voice_fallback`; `.env.example` and Bicep params carry the four names. `event_cue` for restarts gains `restart`.
  Client: shot -> "Name... shot... saved / blocked / wide", goal -> "Goal! Name", foul (+ card once part 2 lands), restart ->
  "Throw-in, Northport" (corner, free kick, goal kick too), out, and the passer's name in the final third (max one every 3 s).
  One at a time, >= 2 s apart, higher priority cuts a lower one off; skipped while narration/recap/tour speaks, cut off when it
  starts; ducks the match bed to 0.5. Clip silence is trimmed in the client. Layer toggle "Callouts", on in Casual / Audio only,
  off in Analyst. Checked in headless Chrome (first-goal chapter, ~4 min): 13 callouts incl. "Goal! Baptiste", no console errors.
  **Deviations:** no "recovered" word (ball recoveries are not cues; nothing would say it); the shot callout says the outcome
  itself, because a separate "saved!" 0.5 s later would be dropped by the one-at-a-time rule. **Owner, open:** listen (EN, then TR).

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
- Live narration on a cache miss: p50 1.58 s / p95 3.60 s (prompt 4, minimal effort, offline eval), so most misses now make the 4 s deadline;
  the slowest still fall back to the template, and deployed misses also pay TTS (p50 ~0.45 s). The demo still uses the pre-generated cache.
- 10 listeners joining in the same second still wait p50 3.8 s for the first message (0.5 vCPU); fine for judging, owner chose to keep 0.5.
- The Verifier checks numbers, names, jargon and code values; it cannot catch invented details without a number or a name. Say so in the README.
- Keep the deployed demo cheap: single container app; scale-to-zero is not ideal for a live demo, so use min 1 replica only during judging.
- iOS Safari background audio untested.
- No claim of blind-user validation unless it actually happens.
- Detector scores may be mediocre on some scenario types; report honestly.

## Working method
- Claude Code (VS Code) writes code; GitHub is the source of truth; one task per session, `/clear` between PRs.
- Chat (claude.ai) is for architecture, briefs, review and unblocking. Reply language: Turkish, direct, practical.
