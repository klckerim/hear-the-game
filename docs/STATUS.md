# Status (update at the end of every work session)

Last updated: 2026-10-26 (README final pass, submission texts, deployed latency with 4 sessions, bug hunt: all done; nothing to deploy). Next: the video (opening shot: the listening view), then the owner's read-through of README and the submission texts. Calendar note: the plan's dates (Day 5 = Oct 24) run ahead of the real calendar; everything up to Day 6 was actually done on 2026-10-21, which is the date in the results files.

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
- **Owner, still open:** trace check in App Insights (content on the chat span); `htg.speech.dropped_stale` count (both deferred to a later session);
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
  is closed.

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
  itself, because a separate "saved!" 0.5 s later would be dropped by the one-at-a-time rule. Owner listened in Chrome (2026-10-23): part 1 closed.
  Follow-up: a sentence waits for a callout already under way (max 3 s) instead of cutting it off mid-name.
- **Part 2, cards (done, 2026-10-23):** fouls carry `card` (`yellow` / `red` / null) from a separate RNG stream
  (`[seed, 0xCA2D]`): 15% of fouls yellow (a booked player gets no second one), 0.6% straight red; seeds 1-30 average 3.1 yellows
  and 0.17 reds per match. Schema first. `test_cards_change_no_other_field` hashes every event without `card` for seeds 1, 2, 3, 7
  against hashes taken before the change (identical); `eval.scenarios` rerun, `scenarios.md` unchanged; the seed-1 file pin was
  re-pinned. `event_cue` carries `card`; the client plays a booking whistle (short + long, louder), the log says "Foul · Yellow card
  · Name", the callout says "Foul... yellow card, Name". Seed 7: four yellows in the opening chapter, one at 83'.
- **Part 3, "Next moment" (done, 2026-10-23):** button (and key N) under Start. `WS /ws?chapter=..&next=1&after=<play clock>`: the
  server starts 30 s before the first goal / saved shot / card more than 30 s after `after` (stopped: the chapter start), so each
  press moves on; `hello.moments` lets the client disable the button when none are left. Jump points are a fixed set (16 for
  seed 7), each warmed once in a thread and cached like the chapters (warm-up 0.2-0.4 s). The client resets exactly as on a chapter
  jump (timeline, score from the warm-up, Why card, log, recap history); the status line (read aloud) says "next moment from 83'".
  Checked in headless Chrome: 19' -> 22' -> 23' -> 36' -> 45' -> 53' and 76' -> ... -> 86' (button disabled), scores right, no
  console errors. **Deploy 1 done by the owner (2026-10-23):** smoke check on the deployed app: healthz ok, new client served,
  `next=1&after=1145` -> window starts 1328 s (22:08), 16 moments (cards included). Owner listened (cards, Next moment, Callouts toggle): parts 2-3 closed.
  Follow-up: the Callouts toggle keeps the listener's choice per group (fan modes / Analyst) instead of resetting on a mode change.
- **Part 4, live commentator (built, 2026-10-23; waiting for deploy 2 and the owner's listening check):**
  `htg/commentary/segments.py` cuts play into segments (dead ball or 10 s; shot + goal are one; seed 7: 375 per match) with flat
  facts (score, team on the ball, up to 4 players, passes, progression, how it ended, shot speed, card, tactical Insight,
  `seconds_available`, 10 after a dead ball). `htg/commentary/commentator.py`: one Foundry call per segment, EN + TR in one call,
  0-2 lines with style and offset, prompt v3; the narration Verifier on the segment facts plus football terms allowed ("first half",
  "kendi yarı sahası"), invented details rejected (header, volley, box, penalty, chips, ...), "press"/"baskı" only with a
  pressure Insight, a word budget of 2.5 per second; per language, a line is dropped only if both fail (no template).
  `services/engine/commentary.py`: one sequential stream per session, backlog skips to the newest segment, a model call shared by
  sessions of the same stretch within 60 s, budget = play time - 3 s, else the verified line an earlier session cached ("fallback"),
  else silence; MAI-Voice in the listener's language only, styles mapped per language. Telemetry: span `htg.commentary.segment`,
  `htg.commentary.lines` / `.dropped` / `.latency_ms`. Flag `COMMENTARY` (Bicep: on; local default off).
  Delay: fan modes connect with `&delay=20&lang=..`; the server sends the first 20 s at once (`replay(lead_s=)`) and stays 20 s
  ahead; stats now follow the play clock too; "What did I miss" and stale checks use the listener's time. Client: commentary on the
  match-time timeline; a goal line cuts anything except a goal sentence under way, otherwise it waits up to 3 s for narration /
  recap / tour / a callout, then is dropped; callouts never start over it; caption tag "live · 2.8 s" / "fallback"; status
  "Live commentary · 20 s delay". Analyst: no delay, no commentator.
  Checked locally against Foundry + MAI-Voice: 9 live lines in 150 s of the first-goal chapter, latency 2.6-4.1 s (cold first call
  11.7 s), every line ready 6-17 s before it plays; headless Chrome: Start -> first packet 334 ms (chapter) / 339 ms (Next moment),
  lines play on the delayed clock, narration takes over, TR works, no console errors. Seen in trials and left to the honesty note:
  the Verifier checks names and numbers, not every adjective ("low delivery", "Rossi held" got through before prompt v3).
  Tests: `tests/test_commentary.py` (fake model; segmenting, unknown name / invented detail, late drop + fallback, backlog, cache
  key, burst). Deploy 2 done by the owner; checked from outside (2026-10-23): live lines arrive with `source: live`, 1.3-3.0 s, and the
  caption tag shows "live · x s" in headless Chrome (Casual). The tag only appears in Casual / Audio only (Analyst has no commentator).
- **Part 5, measured (2026-10-23):** `eval/commentary.py` replays 8 windows (seed 7 chapters + seeds 11-15 from 19', 119 match
  minutes) with the real commentator (Foundry + Verifier + MAI-Voice EN, no cache) on a simulated clock and the client's one-voice
  rules (simplified; narration and callout durations estimated). 30-s windows with speech 21% -> 90% (callouts) -> 97% (+ commentator);
  worst silence 605 s -> 84 s -> 64 s; latency p50 3.09 s / p95 4.77 s vs 17 s budget; 3.1 lines heard per minute; Verifier dropped
  12 lines in both languages (48 EN-only, 41 TR-only); 35 client drops (voice taken); 0 late. One call hung ~10 min (OpenAI default
  timeout), so the commentator's client now has `timeout=20` (not deployed yet; rides along with the next deploy, no extra one needed).
  README: "Live commentary" in What you hear, numbers in Evidence, MAI-Voice in the stack table, diagram, limitation, eval command.
  Owner's choice: no list of invented/odd details in the results (only the 10 verbatim lines the task asks for).
- **Fix (2026-10-23): owner saw no live commentary in Casual.** Server fine (local `HTG_ENV=azure`: hello.commentary true, delay 20,
  10 live lines in 3 min, 0 errors; deployed the same). Cause in the client: the page opens in the last mode (Analyst, stored), Start
  connects without the delay, and switching to Casual kept that session's no-delay start, so no commentator for the whole session;
  a language change also wiped "Live commentary · 20 s delay" from the status line. Now crossing Analyst <-> fan mode while listening
  restarts the same window (chapter or jump) in the new mode, and the status line is redrawn with the delay. Checked in headless
  Chrome (Analyst -> Start -> Casual: "canlı · x sn" lines; Casual -> Analyst: no delay). Needs a deploy (rides along with the next).
  **Closed (2026-10-23):** owner deployed (includes the commentator's 20 s Foundry timeout and the mode-switch fix) and saw the
  "live" tag in all three chapters on the deployed app. Task file moved to `docs/tasks/done/`.

## Features D (2026-10-23; task: `docs/tasks/done/2026-10-24-features-d.md`; deployed and checked by the owner, 2026-10-23)
- **Layout:** match bar above the pitch (match picker, favourite club's matches first and marked "your team"; Live / Highlights).
  Right panel: listening settings only (chapters and Next moment removed from it). Timeline = whole match (0'-90', half-time tick,
  played part shaded, session band(s)); known moments (`hello.moments` / `/matches.json`: goals, saved shots, cards) show from the
  start as hollow markers (button: start 30 s before; card = small yellow/red card), a click on the track starts Live from that
  minute, "First goal at 23'" is a hint line (not a button). Next moment + key N sit at the timeline (disabled in Highlights).
  Timeline is now shown in Audio only too (it is the match control); the Why card stays hidden there.
- **Commentary feed** under the caption (fan modes): last 6 lines, minute + "live · x s" / "fallback", newest on top, dual
  language by caption rules, added when spoken; `aria-live="off"`; hidden in Analyst.
- **Server** (`serve.py`): `/ws?match=&mode=live|highlights&from=`; `from` clamped, whole seconds; warm-up per (match, second) in a
  thread, LRU of 64 (~2 MB each; worst warm-up 0.4 s at 79', copy 8 ms). Live runs to full time (no 15-minute cap; `MAX_SESSIONS`
  kept). A hidden tab closes the socket 2 min after the browser suspends its audio, or after 45 min hidden even if the sound plays
  (owner's choice, 2026-10-23: a locked-screen listener must not be cut off; the task's flat 2 min did that). Start resumes there.
  Checked in headless Chrome by faking `document.hidden`: audio running -> still connected after 135 s; suspended -> stopped,
  "Start picks up at 2:17". Mode switch Analyst <-> fan restarts **where the listener is**
  (Highlights: the clip under way, `from` filters clips), not the session start.
- **Highlights:** windows [moment - 30 s, moment + 15 s], merged; between clips the server waits the delay (the listener reaches the
  clip end), sends `cut {t_from, t_to, score}` and starts the next clip with its own 20 s burst; client re-anchors the play clock
  (1.2 s gap, soft whoosh, minute shown large on the pitch, status line "Next highlight: 34'"). Half-time recap (new `kind:
  half_time`, cached like full time) before the first second-half clip; full-time recap after the last clip, same request as Live
  at 90:00 (seed 7 cache hits). Checked at 40x: seed 7 = 15 clips, 14 cuts, scores from warm-up right (0-1 after 22', 1-1 after
  79'), both recaps arrive.
- **Highlights lengths** (clips only; transitions add ~1.2 s each, recaps ~15-30 s each): seed 7 11.7 min, 33 11.1, 37 12.3,
  47 11.5, 49 11.4, 34 10.7. All inside 8-14, so no stricter moment rule.
- **Commentary cache key** = (match seed, segment id, prompt version, model); start minute dropped. Test: a pipeline warmed to 30'
  cuts identical segments (ids, times, facts) to a kick-off run. 108 cached seed-7 files moved to the new key (12 orphans left).
- **League** (`htg/league.py`): Northport (red), Valemont (blue), Kingsmoor (yellow), Lornbridge (orange), Zekteris (white),
  Thornfield (purple). Web search (2026-10-23): no club named Kingsmoor, Lornbridge or Thornfield, so no spare needed. Zekteris
  squad is all Turkish (owner, 2026-10-23: Tunalı, Karadağ, Akbulut, Ertuğrul, Doğanay, Özbey, Sevim, Kocabaş, Uzunoğlu, Gürsoy, Alkan).
  Fixtures: 7 Northport v Valemont (default, 1-2), 33 Zekteris v Thornfield (2-2), 37 Lornbridge v Zekteris (2-1), 47 Kingsmoor v
  Valemont (2-3), 49 Thornfield v Kingsmoor (2-2), 34 Valemont v Lornbridge (1-3). Seeds 31-60 surveyed, picked for goals; no
  red v orange, yellow v white or blue v purple pairs. `generate(seed, home=, away=)`; test pins seed 7's events hash (identical to
  before the league) and shows seed 31 is the same with two club pairs. meta teams gain `club`; `hello` teams too.
  Server generates fixtures at start (or on a squad change); Dockerfile runs `python -m htg.generate --league`.
  White kit: the ball is drawn dark with a white ring (a white ring on a white ball hid the team).
- **Callouts:** `htg.speech.callouts` keeps existing clips (`--all` remakes); +192 clips for 4 clubs and 44 surnames, now 340
  clips, 3.2 MB (was 1.25 MB). 0 fallback voices.
- **Live on a new match** (local -> Foundry/MAI-Voice, Zekteris v Thornfield from 13', 3 min, Casual EN): 12 live lines, latency
  p50 2.48 s, max 6.99 s (the first, cold call), 0 fallback; narration `llm` for two of three Insights, the goal sentence fell back
  to the template (4 s deadline). Seen once: "Zekteris lead restored!" on 1-0 (invented word; the Verifier does not check meaning).
- **Fix (2026-10-23, owner noticed):** switching match while listening could let a sentence of the old match play over the new one
  (timers checked only the socket; a clip still decoding started after the switch). Narration, recaps, log lines and the full-time
  flag are now bound to the session (`live.gen`). Checked in headless Chrome: a slow old clip is dropped, a same-session clip plays.
  **Changed by the owner (2026-10-23), unlike task 1.4:** switching match or Live / Highlights now stops listening and waits for
  Start (status line, read aloud: "Ready: Zekteris – Thornfield · Highlights. Press Start listening"), so browsing the list or an
  arrow key on the picker never starts a match. Timeline click, a moment and Next moment still start at once. Checked in headless Chrome.
- **Fix (2026-10-23, owner heard it):** on seed 7's 79' equaliser (1-1) the commentator said "Goal! Arda smashes it in — Northport
  lead!" (facts were right; the model inferred a lead, the Verifier does not check meaning, and the line was cached and replayed as
  fallback). Now: segment fact `goal_effect` (takes_lead / extends_lead / equaliser / pulls_one_back, from the score); prompt v4 says
  to use it; Verifier rule: lead words (lead, ahead, in front, öne geç…, önde) only with a lead (after a goal: takes/extends_lead),
  level words (level, equalis…, all square, berabere…, eşit…) only at a level score; "restored", "yeniden öne", "edge of the …",
  "the area" join the invented details. Prompt v4 changes the cache key, so every v3 fallback line is retired (cache refills live).
  Tried on Foundry: all 7 goals of seeds 7 and 33, twice each: 14/14 lines say the right effect, EN and TR, 0 dropped.
  **Re-measured with v4** (`eval.commentary`, same 8 windows, 119 match minutes): windows with speech 97% (same), worst silence
  66 s (v3 64 s), latency p50 2.71 s / p95 3.91 s / max 10.05 s (v3 3.09 / 4.77 / 604 with one hung call), model chose silence 16%
  (v3 4%), 2.8 lines heard a minute (v3 3.1), Verifier dropped 22 lines in both languages (v3 12). Results file keeps both runs;
  README updated.
- **Commentator warm-up (2026-10-23):** one throwaway model call when the server starts (`warm()`, not verified, not cached), as a
  broadcast has its commentator ready before kick-off. Measured locally: warm-up 2.5 s, then the first listener's first live line
  1.84 s (the first call after a start used to take 7-12 s). **Not done, by the owner's rule:** pre-filling the fallback cache before
  deploy (demo-only; a real match has no pre-made lines). The v4 cache starts empty and fills as people listen.
- **Timeline history + clean match switch (2026-10-23, owner noticed):** a start at minute 60 showed no Insights (detection takes
  minutes; those found during the warm-up were never sent), so the Why card was hard to reach in Live. `warm_up` now keeps the
  Insights and shot / goal cues before the start in `pipe.history`; `hello` (and each Highlights `cut`, for the stretch between clips)
  carries them, and the client draws them at once, selectable for the Why card. Seed 7 from 60': 10 Insights, 22 shots, 1 goal.
  Switching match now clears the old match's caption, feed, log, markers and Why card. Checked in headless Chrome; tests for
  `history` in hello and cut. (Feed rule changed in the pre-freeze round, see below.)
- **Commentary feed scrolls (2026-10-23, owner asked):** keeps the match's last 60 lines (was 6) in the same fixed box; the list
  scrolls (mouse, touch, arrow keys once focused; thin scrollbar), newest on top. A listener reading older lines keeps their place
  when a new line arrives; at the top the new line shows. One grid for the list, so "live · 12,4 sn" and "fallback" rows align.
- **Layout redesign, "broadcast desk" (2026-10-23, owner's brief + 4 changes agreed in chat):** player bar = match picker,
  Live / Highlights, score + clock, then Start / Next moment / Catch me up + status line; sticky on desktop, the transport row fixed
  to the bottom on phones (same buttons). Desk: pitch (height capped to fit 800-900 px) + timeline + Why (only when a marker is
  selected) left; listening column right: mode switch (kept visible: the jury must see Analyst), caption large, commentary feed
  filling the height (Analyst: "Right now" + stats instead), recap list, Settings in a closed `<details>` with a summary ("Casual ·
  EN · None"; commentary language, club, player, layers, voice note, install). Hide pitch sits on the pitch corner; the sound tour
  is a first-visit banner (Take the tour / ×, same localStorage key). DOM order = phone order (mode, caption, pitch, timeline, Why,
  feed, settings); desktop columns by grid areas on three wrappers (one flat grid would couple the two columns' row heights).
  Breakpoint 860 px (not 720: a 768 px tablet would get a ~340 px pitch). Headless Chrome, screenshots in `out/layout/`:
  1440x900 and 1280x800 show player bar, pitch, timeline and caption without scrolling; 390x844, 360x780, 320x640 show Start
  without scrolling and the caption above the pitch; no horizontal scroll anywhere; no console errors; Casual, Analyst, TR checked.
  After the owner's first look: Settings summary reads "Casual · Commentary EN · ★ Northport" / "No favourite club" (was "None");
  Hide pitch readable while pressed; the phone page's bottom padding follows the fixed bar's measured height (ResizeObserver on the
  border box, so the safe area counts), so "What did I miss?" and Settings never sit under it (checked with the bar 60 px taller).
  Default commentary language already follows the browser (TR browser -> TR, else EN) until the listener picks one (remembered).
  Second look: the longer Settings summary (no-wrap) made the listening column 405 px wide on a 390 px phone, so Chrome zoomed the
  page out and the fixed bar covered the closed Settings; columns are now `minmax(0, 1fr)` (checked desktop -> 390/360/320, TR and
  EN: width = screen, scale 1, Settings visible above the bar). `/matches.json` teams carry the outfield players, so the favourite
  player list is filled before Start (it waited for the session's hello).
  Start / Stop changed the button's width, so Next moment and Catch me up moved on every press (desktop), and Start's min width could
  push Catch me up off a 320 px screen: Start has one width on desktop (11em, the longest label), the phone row is
  `minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)`. Checked at 1280 / 390 / 320, TR and EN, idle and playing: positions identical.
  Timeline in Highlights (owner asked): a click, a moment marker or Next moment used to switch to Live. Now they stay in the chosen
  way to watch: Highlights plays the clip at or after that point (the last clip if none is left; the server already starts
  Highlights from `from`), Next moment = the next clip; Live unchanged. Bands show every clip. Checked in headless Chrome.
- **Checks:** 99 tests pass. Headless Chrome: all six matches start in Live and Highlights, timeline click (45') works, favourite
  club marks the right side, no console errors, 375 / 320 px no horizontal scroll.
- **Deployed and checked by the owner (2026-10-23).** Task file is in `docs/tasks/done/`.
- **Client split (2026-10-25; task: `docs/tasks/2026-10-25-split-client.md`):** `web/live.html` split into `web/app.css` + `web/js/*.js`
  (classic `defer` scripts, same order, code moved byte for byte), no behaviour change, served by an allow-list in `serve.py`. Headless Chrome: Start, `hello`, 0 console errors.

## Pre-freeze round (2026-10-25; task: `docs/tasks/2026-10-24-pre-freeze.md`)
- **Listening caption:** after Start the caption says "Listening · the commentator speaks in a few seconds" (fan modes) or "Listening ·
  tactical notes appear when something changes" (Analyst), TR and EN, until the first sentence; Stop, a match switch and the end of the
  tour bring back the idle text (`idleCaption()`; redrawn on a language change while nothing has been said). A jump (Next moment,
  timeline, moment marker) keeps the last sentence on screen (`stopListening(msg, resuming)`; owner noticed); an Analyst <-> fan
  mode switch shows the new mode's listening text (the old line belonged to the other delay; owner noticed).
- **Feed on desktop:** `.d-listen .feed { contain: size }` (>= 861 px), so the feed's lines no longer set the row height; the pitch
  column and the 220 px floor do, and the list scrolls inside. Not checked visually by Claude (owner: 1440x900, 1280x800).
- **Feed per session:** the feed stays only when the new session is the same match, same Live / Highlights, and starts at or after the
  newest line (`continuesFeed` above `resetLive`): Next moment, a forward timeline click, a mode switch that resumes. A match switch,
  Live <-> Highlights (cleared at once), a jump back, or Start after Stop clears it. `addFeed` skips a line already there (segment id
  + time). A line joins the feed when it ends or is cut off (owner asked: the caption shows the line under way, the feed what was
  said; with Narration off it joins at once). Parts 0-2 committed (`6f3d61b`, `3aa6b69`; ruff + 105 tests pass).
- **Submission drafts:** `docs/submission.md` (name, tagline, pitch ~100 words, description ~360, category, judge instructions,
  tech list); numbers only from README / `eval/results/`, layout sentences marked `<!-- UI -->`. Live URL: https://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/
- **Deployed and checked by the owner (2026-10-25):** feed height at 1440x900 / 1280x800, Highlights 76' -> Live 36', Live ->
  Highlights, Stop -> Start, forward Next moment, Analyst <-> Casual caption: all OK. Task file moved to `docs/tasks/done/`.
- **iOS Safari (owner, 2026-10-25):** Live started, screen locked after the first line: commentary still playing after 3 minutes;
  on unlock the feed held the lines spoken meanwhile. One phone, one run; README may say "worked on one iPhone in Safari", not more.
- **Azure credit** ends after Nov 10 (owner); `minReplicas` stays 1.
- **Phone transport row (owner saw it):** in Highlights the long "Ready: Zekteris – Thornfield · Highlights. Press …" status pushed
  the bar's content off screen. Cause: `.p-ctl` is a wrapping flex column, and in a multi-line flex container items stretch to the
  line's width, which the no-wrap status sets. Fix: `flex-wrap: nowrap` on phones (the status then ellipsises), and the
  ready line drops "Press Start listening to begin" (Start sits beside it; screen readers still hear the whole status). Needs a deploy.
- **Match picker (owner asked: the native select wrapped names on phones and looked plain):** a button with the current match
  (club-colour dots, broadcast face, ▾) opens a list of match cards; your club's matches first with a "your team" badge, the current
  one marked with an amber edge (`aria-current`). Cards are buttons, not radios (an arrow key must not switch the match); Escape or a
  click outside closes. A club name never breaks; a pair wraps between the clubs. Not checked visually by Claude. Needs a deploy.
- **Close timeline markers (owner saw it):** two Insights a few px apart: the newest covered the older one's hit area, so the older
  could not be selected. Now the selected marker is raised (z-index 3) and a second tap on it selects the next marker of the same
  lane within 22 px, in match order, round again (`nextOverlap`; pointer clicks only, Enter keeps its marker). Needs a deploy.
- **Open for tomorrow (owner heard it, not looked at yet):** at a big moment a commentator line was cut off just as it started by
  another voice (a female voice, likely the narration sentence or the device voice); the line still showed in the feed.
- Foundry eval refresh (2026-10-25, task `2026-10-25-foundry-eval-refresh.md`): prompt 5, 50 Insights per persona, runs `narration-prompt5-fan/analyst-2026-10-25`. Groundedness fan 4.72 EN / 4.66 TR, analyst 4.92 / 4.92 (was 4.99 on prompt 3: mostly two-exclamation chance lines and numberless fan lines; 3 rows of 200 scored 2, listed in the file); fluency 3.08-3.40. `eval/foundry_eval.py` got `--name`; items file now sits next to `--out`.

## Hardening (2026-10-26; task: `docs/tasks/done/2026-10-26-hardening.md`; deployed on its own, not with listen-view: owner's decision)
- **Prefs:** a session keeps only the latest valid `set_mode` / `set_favourite` (`keep_pref`, validation shared with
  `apply_listener_message` via `run_local.listener_pref`); every other client message is dropped. Before, each one was stored for the whole session.
- **Recaps:** one "What did I miss?" recap per session at a time, then a 20 s cooldown (`RecapGate`, monotonic clock); requests in
  between are ignored (the client's own timeout already falls back to its local recap). Recap work runs on its own
  `RECAP_POOL` (2 threads) so it cannot starve narration and commentary. Full-time / half-time recaps are not gated.
  Client follow-up (`web/js/session.js`): a press within 25 s of the last recap replays it (`live.recapAt`, `RECAP_REPLAY_MS`)
  instead of sending a request the server would ignore and sitting on "Preparing…" for 30 s.
- **Sessions per IP:** at most 4 open sessions per client IP (`MAX_SESSIONS_PER_IP`), refused with the same 1013 "busy"; counted from the
  live `sessions` set, so a closed or failed session frees its slot. **Deviation from the task:** the IP is the *rightmost*
  `X-Forwarded-For` hop, not the first: Container Apps ingress appends the real address and keeps whatever the client sent before it
  (Microsoft Learn, "Ingress in Azure Container Apps", HTTP headers), so the first hop could be spoofed to dodge the cap.
- **NaN:** `?delay=nan|inf` -> no delay; a NaN / infinite `since_min` -> the default last 10 minutes. `.env.example` has a placeholder Foundry endpoint.
- Tests: 6 new (112 pass). Not tested on the deployed app.
- **Not doing (decided):** WebSocket `origins=` (a wrong list breaks the demo and local dev); a server idle timeout (the client already
  stops a hidden tab, and a timeout would cut locked-screen listeners; a script is bounded by the IP cap and the deployment TPM); a disk
  cache size cap (falls away with the recap gate); Foundry portal links in `eval/results/foundry_eval.md` stay (jury evidence, no
  credential); squad names that match common real surnames stay (fictional clubs). `htg/validate.py` reads `truth.json`: it is the
  generator's validator, not a detector, engine or agent, so it is allowed; not moved.
- **Owner, open:** a subscription budget with an email alert; check the Foundry deployment's TPM limit (the real hard cap; 429 falls
  back to templates); confirm `web/icon*` are self-made; check the MAI-Voice preview terms allow a public demo; optionally commit with
  the GitHub noreply email.

## Listening view (2026-10-26; task: `docs/tasks/done/2026-10-26-listen-view.md` + the owner's addendum; deployed by the owner, 2026-10-26)
- **Commentator cut-off fixed** (`web/js/speech.js`): a narration sentence now waits for a commentator line under way (max 6 s, 8 s
  after a goal line) instead of cutting it; `sayHeld` keeps the voice slot so no new line starts in the gap; the caption changes when
  the sentence starts, not while it waits. Recaps still cut non-goal lines. Heard by the owner at a goal on 2026-10-26: no cut-off.
- **Two views, one page** (`web/js/listen.js`, views block in `web/app.css`): `body[data-view]`; first visit opens the listening
  view, `?view=listen|desk` overrides and is stored in `htg.view`. "Show the pitch & data" / "Listening view" (desk header, beside the
  language) switch both ways without stopping the sound. The listening view plays in Audio only through `setMode(m, false)`, so
  `htg.mode` keeps the desk's choice (Analyst -> listen -> desk is Analyst again, also after a reload).
- **Listening view** (calm, mobile first, max 560 px): a "now playing" card (score, clock, caption as the subtitle), Start / Stop as
  the strongest element (72 px), Next moment + Catch me up (stack below 360 px), Live / Highlights, status, "Choose a match" (h2) with
  the always-open cards, tour offer, a hint line (touch: lock-screen hint; desktop: Space / N; chosen by CSS), the switch.
  Four desk elements (caption, Live / Highlights, match list, tour banner) move into this order and back to their places.
- **Match cards:** read as "Northport versus Valemont" (TR "Northport – Valemont maçı"), never the score; dots `aria-hidden`. In the
  listening view a tap starts that match at once on the Start path, synchronously (iOS audio unlock), and focuses Start/Stop; the
  match already playing only moves focus. The desk keeps "a new match waits for Start".
- **Checked** (headless Chrome against local `serve`, 1440 / 390 / 340 / 320 px): reading order = visual order; no horizontal scroll;
  no target under 48 px; text >= 18 px except the 14 px "your team" badge on a card; only `#status` is a live region here; a card
  starts a session (hello, status); view switches keep the same socket; the desk comes back exactly as before; touch hint under
  touch emulation; TR texts; no console errors. Contrast: muted text 6.3:1 on the card, chalk 14.5:1. Six screenshots (two were
  wasted on a stale headless browser).
- **Deviations:** order follows the addendum (Next moment / Catch me up before Live / Highlights); the status line stays visible
  (it is the only spoken state: connecting, lost, reconnecting); the tour banner stays, in neutral colours. Live / Highlights does
  not start on its own in the listening view (same as the desk: Start or a card starts).
- **Polish after review** (2026-10-26): score card is one grid row (home | score | away, clock under; score 48 px desktop / 40 px at
  390, names scale to fit at 320); the idle status is the ready line, "Not connected." only after a failure; phone cards 20 px / 14 px.
- **One language for screen and commentary** (owner's decision): the desk's commentary-language control is gone, `lang()` is the
  interface language, a stored `htg.commentary` is removed on load; in the listening view the select is replaced by two buttons at the
  top right ("English" / "Türkçe", each in its own `lang`, `aria-pressed`, group "Language" / "Dil"; one double tap, no picker wheel;
  beside the title down to 375 px, under it on narrower screens); changed while listening in the desk, the status line says "Commentary in English" / "Anlatım Türkçe"; in the listening view
  it is only redrawn in the new language. The listening view's status leaves out "20 s delay" (the desk keeps it). README paragraph updated.
- **Listening view follows the device language** (owner, 2026-10-27, after VoiceOver on macOS still mixed voices on a switch): the two
  language buttons and the listening view's spoken switch notice are gone; the view has no language control. Default: stored `htg.lang`,
  else the first `navigator.languages` entry starting with "tr" or "en", else "en"; `?lang=en|tr` overrides and is stored (like `?view`).
  The desk's header select is unchanged and sets `htg.lang` for both views. README and `docs/submission.md` say so. The README's phone
  screenshot (`docs/img/listen-phone.png`, alt text "English and Türkçe buttons at the top") still shows the old buttons: owner retakes it.
- **Caption follows a language switch** (owner, 2026-10-27): `#caption` kept the old language's sentence (a recap stayed until the next
  line) and its tag fell back to "Narration". `setCaption` now keeps the sentence (EN + TR) and a tag builder; `applyI18n` redraws both
  at once in the new language while the voice finishes the sentence in the old one; a line without the new language empties the caption.
  Checked in a local session (desk, templates): narration, Catch me up recap, one-language line, stopped state; no console errors.
- **Owner, VoiceOver on iOS (passed 2026-10-26 with the old language buttons; steps 1 and 7 changed 2026-10-27, re-run them):** 1. open the
  app: the listening view, in the device's language; swipe from the top: title (no language buttons), tagline, score, clock, caption, Start, Next moment, Catch me up, Live, Highlights, status, "Choose a match",
  the cards, tour, hint, "Show the pitch & data". 2. double-tap a card: sound starts on the first tap, focus lands on Stop, VoiceOver says the status. 3. double-tap Stop,
  then Start again. 4. Next moment, then Catch me up (hear the recap). 5. lock the phone for a minute: sound continues. 6. "Show the
  pitch & data", then "Listening view": the sound never stops. 7. open `?lang=tr` (or pick Türkçe in the desk's header select,
  then "Listening view"): screen and commentary in Turkish, VoiceOver in one voice; repeat 1-2.

## README final (2026-10-26; task: `docs/tasks/done/2026-10-26-readme-final.md` + the owner's addendum; no deploy needed)
- README (`31486dc`): first screen is title, pitch line, Live demo · category links (no video link yet: owner adds it later), intro,
  Try it, "How it works in 3 steps", two screenshots side by side (`docs/img/listen-phone.png` 390x844, `docs/img/desk.png` 1440x900
  Casual; owner approved images after all), and a "Challenge fit" table against Official Rules 4.1 (stage labels i a-e, ii, iii-vi
  taken from the owner's addendum; owner to check them against the rules text). Also: listening-view paragraph, "Why Foundry"
  (prompts 3 and 5 had Foundry evaluations, prompt 4 only the offline eval: worded so), fluency sentence, honest iOS / VoiceOver line,
  a real Verifier blind spot ("at the break" at minute 9), public demo limits, Not built: Media Session, user study, auto-eventing.
- Screenshots were taken from local serve with `HTG_ENV=azure`: with `.env` as it is (`HTG_ENV=local`, `COMMENTARY=on`) the local
  stub commentator tags lines "live · 0.0 s", which would mislead. Not a bug in the deployed app.
- `docs/submission.md` (`c7fbe22`): judge steps follow the listening view, one EN/TR switch, the desk one tap away; session limit 4 per IP.
- Deployed latency (`4e10302`): `eval/latency.py --watch live|highlights`. 4 sessions, 3 min, from Istanbul: Live hello p50 2.2 s /
  p95 3.0 s, state p95 202 ms, longest gap 1.6 s, Insight -> speech p50 334 ms (4, all verified with audio); Highlights hello p50 2.0 s /
  p95 2.7 s, longest gap 2.4 s (probably a clip cut), no narration in the 3 minutes. 0 session errors, no busy refusals.
- Bug hunt (headless Chrome, local serve, `HTG_ENV=local`): 6 matches x Live/Highlights x EN/TR in the listening view at 390 px (tap card,
  hello, Next moment, Catch me up, Stop) and the desk at 1440 in Audio only / Casual / Analyst: 0 console errors, 0 uncaught exceptions,
  Start/Stop label, match, watch and status right at every step. Nothing fixed, no commit. For the owner (not fixed, minor):
  - After Stop the status says "Ready: <match> · Live" although Start resumes from the minute where it stopped (e.g. 7').
  - The template recap in the first minute reads "After 0 minutes it is Northport 0, Valemont 0" (the agent is used when deployed;
    the template is its fallback).

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
- 4 listeners (the per-IP cap) joining in the same second wait p50 2.2 s for the first message (0.5 vCPU, 2026-10-26); fine for judging.
- The Verifier checks numbers, names, jargon and code values; it cannot catch invented details without a number or a name. Say so in the README.
- Keep the deployed demo cheap: single container app; scale-to-zero is not ideal for a live demo, so use min 1 replica only during judging.
- iOS Safari background audio: worked once on one iPhone (locked screen, 3 min, 2026-10-25); not tested further.
- No claim of blind-user validation unless it actually happens.
- Detector scores may be mediocre on some scenario types; report honestly.

## Working method
- Claude Code (VS Code) writes code; GitHub is the source of truth; one task per session, `/clear` between PRs.
- Chat (claude.ai) is for architecture, briefs, review and unblocking. Reply language: Turkish, direct, practical.
