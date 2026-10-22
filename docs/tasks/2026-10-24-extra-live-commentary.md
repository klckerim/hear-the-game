# Extra task (added 2026-10-22): live commentator, callouts, cards, highlight jumps

Status: an addition to the plan, not a replacement. Features A, B, C and the language split are done (STATUS, 2026-10-22), so this
runs on Oct 23-24 and the code freeze stays **Oct 25 noon** with buffer; video recording Oct 25 afternoon. Parts are independent and
ship in this order; each has a feature flag. **Cut-off Oct 24 20:00:** whatever is not smooth by then is switched off; parts 1-3 stay
if they work. **Commit after each part** (tests green), so a cut never loses the earlier parts. **Deploy only twice**, and only
the owner runs `azd deploy`: (1) after parts 1-3, (2) after part 4 or after the decision to switch it off. Tell the owner when a
deploy point is reached; do not run `azd` yourself.

Current state to build on (read the code, not memory): `event_cue` already carries `x, y` and `speed_mps` for shots/goals (features C);
the evidence timeline and the Why card follow the match clock; chapters 0' / 19' / 76' with a 15-minute session (Late drama ends at
90'); "Catch me up" and the full-time recap come from the Recap agent (`htg/recap/`); interface language and commentary language are
separate (dual caption); narration voices are `SPEECH_VOICE_EN` / `_TR` (Sonia / Emel). The MCP server was dropped.

Why: in the demo the narrator speaks about once in six minutes (only tactical Insights, by design). A fan, and a judge, needs a
match that talks. The rules name "real-time narratives". Selection rule as always: only what a judge notices in the video or the
first minute of the demo.

Done when:
- In fan modes the match is never silent for long: short callouts for shots, saves, goals, fouls, cards, restarts, and names in
  the final third; a live LLM commentator adds natural lines with emotion, in a male voice, in sync with the sound.
- A "Next moment" button jumps to 30 s before the next goal, saved/on-target shot or card.
- Measured in `eval/results/commentary.md`: speech coverage and longest silence before vs after, commentator latency vs the delay
  budget, Verifier pass rate, dropped lines.
- `ruff check . && pytest` pass without Azure; deployed; owner listened to all three chapters.

## 0. Voices (owner, 10 min, before part 1)
**English is the primary language** (the jury, the video, README); Turkish is second. Everything here (styles, excitement,
callouts, commentary quality) must work in English first, then Turkish. Male commentator voices, both MAI-Voice with emotion styles:

| | Primary | Styles used | Fallback (male) |
|---|---|---|---|
| EN | `en-US-Ethan` (MAI-Voice-2.1 / -Flash) | `excited`, `shouting`, `surprised`, `joyful`, `neutral` | `en-US-GuyNeural` (`excited`, `shouting`) |
| TR | `tr-TR-Aydın:MAI-Voice-2-Flash` (only this model is offered for Aydın on our resource; dotted "ı") | `excited`, `serious`, `curious` | `tr-TR-AhmetNeural` (no styles) |

**Owner checked on 2026-10-23:** both voices work on our resource. The model differs per language, so the full voice name
(voice + model) is one config value per language. Copy names exactly from the playground / voice list; do not normalise "ı" to "i".
At startup, log the configured names; on an "unknown voice" error fall back as described below.

Try them in the Foundry text-to-speech playground (aka.ms/foundry-text-to-speech), EN first: "Okafor... shot!",
"Oh, what a challenge! The referee goes to his pocket, yellow card!", then the TR equivalents.
Facts checked on 2026-10-22 (MS Learn, "MAI-Voice in Azure Speech"): prebuilt MAI voices need no registration (only voice
cloning is gated); same Speech resource, SDK and SSML, only the voice name changes; Sweden Central is a supported region; billed
per character like other TTS (see the Azure Speech pricing page; our volume is a few hundred thousand characters at most).
Voice names: EN `en-US-Ethan:MAI-Voice-2.1-Flash`, TR `tr-TR-Aydın:MAI-Voice-2-Flash`. Flash for live lines and callouts.
**MAI-Voice is in public preview (no SLA).** Config: `SPEECH_VOICE_COMMENTARY_EN` / `_TR`, a style map, and
`SPEECH_VOICE_COMMENTARY_FALLBACK_EN` / `_TR` (Guy / Ahmet), in `.env` and Bicep. On a synthesis error, retry once with the
fallback voice (styles dropped if unsupported) and count it in telemetry; switching voices must be a config change, not a code
change. README labels the voices "MAI-Voice-2.1 (preview)". Existing narration clips keep their current voices; mixed voices are acceptable.

## 1. Callouts (deterministic, no LLM, ~4 h)
1. `htg/speech/callouts.py`: a fixed list of short clips per language and tone (normal / excited), pre-generated once with the
   commentary voice (EN `excited`/`neutral`, TR `excited`/`neutral`) into `data/cache/callouts/` (expect ~140 clips, < 2 MB):
   every player's surname; club names; words: shot, saved,
   goal, foul, yellow card, corner, free kick, throw-in, goal kick, out, blocked, wide, recovered (EN and TR equivalents).
2. Client: map `event_cue` (it has `player_id`) to "name + word" sequences, e.g. shot -> "Okafor... şut!" (excited), save ->
   "kurtardı!", out -> "taç, Northport", foul with card -> "faul... sarı kart, Silva". In the final third, the name of the player
   who receives or carries the ball, at most one name every 3 s. Rate limit: one callout at a time, at least 2 s apart, priority
   goal > shot > save > card > foul > corner > free kick > throw-in > goal kick > name. Callouts play on the narration bus with
   ducking and yield to narration, commentary and recaps (skip if a sentence is playing). They use the commentary language.
3. On in Casual and Audio-only; off in Analyst (layer toggle "Callouts" in Layers).

## 2. Cards (generator, ~1 h)
1. Fouls get a `card` field (`yellow` / `red` / null) from a **separate** RNG stream seeded from the match seed, at a realistic
   rate (about 3-4 yellows per match, red rare). Schema first (`event.schema.json`), then code.
2. Every other field of every event must stay identical: test with a hash over events without `card` for seeds 1, 2, 3, 7, and
   rerun `eval.scenarios` to show `scenarios.md` is unchanged. If anything else changes, stop and tell me.
3. `event_cue` carries `card`; the client plays a whistle variant; callouts say it.

## 3. "Next moment" (~2 h)
Moments = goals, saved or on-target shots, cards (from events). Button "Next moment" (TR/EN) starts a new replay at the next
moment after the current match time minus 30 s; the warm-up for that minute runs in a thread and is cached per minute; narration
cache misses go to Foundry as usual. Keep chapters as they are. The jump starts a new session window: the timeline, score, Why
card and "Catch me up" history must reset or carry over consistently (no markers from the old window on the new axis).

## 4. Live commentator (LLM, ~1 day)
**Decisions with the owner (2026-10-23), these win over the text below where they differ:**
- **Live is the primary path; no pre-generation of the commentary.** The product claim is "live data -> natural commentary", and
  the jury opens the app at any time, unattended. Every session generates its lines live; a 20-30 s broadcast delay is normal
  and is still called "live" (as on TV). The cache is only a safety net: when a live line is late or Foundry / MAI-Voice fails,
  play a verified line cached for that segment from an earlier session, else callouts only. Sound never waits, the demo never
  crashes. The caption tag shows "live · 2.1 s" or "fallback" so liveness is visible; telemetry and `eval/results/commentary.md`
  report latency p50/p95 vs the budget, late drops and fallback use. (This replaces "pre-generate the commentator lines for the
  three chapter windows" in 4.1.)
- **Ordering = a timeline by match time, not a FIFO by arrival.** Each line carries `t` = segment end + `offset_s`; the client
  puts it in `live.due` with every other message and plays it when the delayed play clock reaches `t`.
- **One generator per stretch, sequential:** facts + last 3 lines -> Foundry -> Verifier -> TTS -> send, then the next segment
  (the "last 3 lines" context needs order; segments ~5-10 s, model + TTS ~2-4 s). If a backlog builds, skip to the newest
  finished segment and count the skipped ones (the commentator never lags behind; callouts fill the gap). Shared by all
  listeners of the same stretch (lock); later listeners get it from the cache.
- **Deadline on the server:** a line ready later than `play time - 3 s` is dropped and counted, never sent.
- **One voice at a time on the client, by priority:** goal line (cuts anything) > half-time / full-time recap > tactical
  narration > commentator line > callout. A commentator line whose slot is taken waits a few seconds, then is dropped as stale;
  callouts yield to it.

1. **Broadcast delay.** In Casual and Audio-only the client plays everything (sound, callouts, narration, commentary) 20 s behind
   the server stream; Analyst keeps today's 300 ms. Chosen at start, shown as "Live commentary · 20 s delay". This is what lets the
   commentator be late without being out of sync. Everything drawn (ball, timeline playhead, markers, Why card, stats, clock)
   follows the same delayed play clock, so picture, sound and words stay together. A mode change mid-session keeps the delay
   chosen at start.
   **No visible wait at start:** the server sends the first 20 s of match data at once (burst), then continues in real time, so the
   client's buffer is full immediately and playback starts as soon as the listener presses Start (same for chapters and jumps).
   Pre-generate the commentator lines (and clips) for the three chapter windows of seed 7 with a pregen command, like the narration
   cache, so chapter starts never wait for the model. Live generation is for "Next moment" jumps and anything not cached; that is
   where the 20 s budget matters. Test: time from Start to first sound is under 2 s locally for every chapter.
2. **Segments.** `htg/commentary/segments.py`, deterministic: a segment ends at a dead ball (out, foul, shot, goal, period end) or
   after 10 s. Facts per segment: minute, score, team in possession, up to 4 players involved (in order), pass count, progression
   (own half / midfield / final third), how it ended (event, restart type, card, shot outcome and speed in km/h), the current
   tactical Insight if one was just detected, and `seconds_available` (segment length).
3. **Commentator.** One Foundry call per segment with the facts, the last 3 lines said (no repetition), persona fan; it writes
   **both languages in the same call** (EN first) but only the listener's commentary language is synthesized; the other text feeds
   the dual caption (language-split task). Output JSON `{"lines": [{"en", "tr", "style": "calm|lively|excited|explosive", "offset_s"}]}`, 0-2 lines, length
   scaled to `seconds_available` (about 2.5 words per second). Silence is allowed. Prompt: real radio commentator, football jargon,
   short exclamations ("Ooo!", "Kurtardı!"), never invent a detail that is not in the facts (no "volley", "header", "top corner",
   no injuries, no causes). `COMMENTARY_PROMPT_VERSION = 1`.
4. **Verifier.** Existing rules with known facts = the segment facts; allow football terms; a failing line is dropped (no template;
   callouts cover the gap). Lines that would arrive later than `delay - 3 s` are dropped and counted.
5. **Speech.** Commentary voice; style from the line, mapped per language (EN `explosive` -> `shouting`, `excited` -> `excited`,
   `lively` -> `joyful`, `calm` -> `neutral`; TR `explosive`/`excited` -> `excited`, `lively` -> `curious`, `calm` -> `neutral`).
   Goals preempt whatever is queued. Tune and listen in English first.
6. **Sharing and cost.** The replay is deterministic, so lines (both languages) are cached per (seed, start minute, segment id,
   prompt version) and clips per (line, language, voice): the first listener of a stretch generates them live, later listeners replay them. Say so in the README
   ("generated live by Foundry, cached for replay"). One generator per stretch (lock), not one per listener.
7. **Recaps.** At `period_end` the commentator hands over to the Recap agent (features B) for the half-time / full-time summary.
8. Telemetry: span per segment (facts size, lines, verifier drops, latency vs budget, cache hit).
9. Flag `COMMENTARY=on|off` (server env); off = callouts + current narration only.
10. Tests (fake model): segmenting is deterministic; a line with an unknown name is dropped; late lines are dropped; cache key.

## 5. Measure and document
`eval/commentary.py` over the three chapters of seed 7 and 5 reporting seeds: share of 30-s windows with speech and the longest
silence, before (narration only) vs after (callouts, + commentator); commentator latency p50/p95 vs the 20 s budget; lines per
minute; Verifier drops; late drops. Quote 10 consecutive lines verbatim (TR and EN) in `eval/results/commentary.md`, and list any
invented detail you find. README: "Live commentary" section, numbers, the honesty note (the Verifier checks names and numbers,
not every adjective). STATUS. Move this file to `docs/tasks/done/` when finished.

## Out of scope
Changing the generator beyond cards, speeding up playback, video auto-eventing, multi-agent orchestration.
