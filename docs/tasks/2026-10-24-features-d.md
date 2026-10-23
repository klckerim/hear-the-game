# 2026-10-24 (after part 4 of the live-commentary task): match choice, Live / Highlights, match controls by the pitch

Context: one fixed demo match with three chapter buttons at the top of the control panel is a demo, not a product. A fan picks a
match, watches it live or as highlights, and controls the match where the match is (pitch and timeline). Data and voice are
generated live (part 4: live commentator, live narration, cache only as a fallback), so a new match needs no pre-generation.
English first. See "Scope and token budget" in CLAUDE.md. Vanilla JS stays.

Current state to build on (read the code, not memory; STATUS 2026-10-23): live commentator in the fan modes behind a 20 s delay
(burst of the first 20 s, sequential stream per session, 20 s Foundry timeout, fallback cache git-ignored at runtime); callouts,
cards and Next moment; switching Analyst <-> fan mode restarts the same window; chapters 0' / 19' / 76' with 15-minute sessions;
`eval/results/commentary.md` (speech in 97% of 30-s windows). Keep all of that working; this task changes how a session is chosen,
not how it sounds.

Decisions (owner + chat, 2026-10-23):
- **No playback speed-up.** Speech cannot be sped up and the commentator would fall behind; sonification at 2x loses meaning.
  Instead: **Highlights**, the match's moments back to back at normal speed (TV-style), about 10-12 minutes.
- **Two ways to watch:** **Live** (whole match from the chosen minute, 1x, live commentator) and **Highlights**.
- **Match controls move next to the pitch;** the right panel keeps only listening settings.
- **Chapters go away** (Kick-off / First goal / Late drama): the full-match timeline replaces them.
- Northport - Valemont (seed 7) stays the default match, with its caches.

Done when:
- A match bar above the pitch: match picker (fixture list) and Live / Highlights. The right panel no longer has "Start from".
- The timeline spans the whole match (0'-90'), shows the known moments, and a click (or Enter on a marker) starts from that minute;
  the Next moment button (and key N) sits at the timeline.
- Highlights plays every moment of the match at 1x with short transitions, plus the half-time and full-time recaps.
- At least 5 matches between fictional clubs can be picked; any of them works end to end with live narration and commentary.
- `ruff check . && pytest` pass without Azure; owner deploys and checks desktop and phone width.
- **Cut order if time runs out:** click-to-start on the timeline first, then match choice (keep seed 7 only). Highlights, the
  new layout and the commentary feed are the ones to keep.
- **Commit after each part** with tests green. **Deploy once at the end**, by the owner (`azd deploy`); tell the owner when ready.
  Do not run `azd`. Code freeze: Oct 25 noon.

## 1. Layout (~1.5 h)
1. **Match bar** above the pitch, one row on desktop, wraps on phones: match picker ("Northport v Valemont" etc., favourite club's
   matches first, marked), Live / Highlights segmented control, and the clock/score already there. Labels from the `T` dictionary,
   EN first.
2. **Right panel:** Start/Stop, sound tour, listening mode, commentary language, favourite club, favourite player, Callouts and other
   layers, "Catch me up". Remove the chapter group and its strings.
3. **Timeline:** the axis becomes the whole match (0'-90', half-time tick). Played part shaded; markers as today (goals, shots,
   Insights) plus the known moments from `hello.moments` (cards included) shown from the start, so the listener sees where the
   action is. The session's window (Live: from the start minute; Highlights: the clips) is drawn as a band. Next moment button at
   the right end of the timeline. Keep markers keyboard-accessible.
4. Changing match or Live/Highlights while listening restarts the session cleanly (same reset as a jump today).
5. **Live commentary feed** (fan modes, ~1 h): the owner noticed the commentator is almost invisible on screen. Under the caption
   (or in the right panel on desktop), a short scrolling list of the last ~6 commentator lines with their match minute and the
   "live · 2.8 s" / "fallback" tag, newest on top, in the commentary language (dual line rules as in the caption). It follows
   the delayed play clock (a line appears when it is spoken, never before). Hidden in Analyst; `aria-live="off"` (the caption
   already speaks). It makes "live" visible in the video and helps anyone watching without sound.

## 2. Live from any minute (~1 h)
1. Server: `/ws?match=<id>&mode=live&from=<seconds>` replaces `chapter=`. `from` is clamped to the match; warm-up for that minute
   runs in a thread and is cached per (match, minute) like today's chapters and jump points.
2. A Live session runs to full time (not 15 minutes). Keep `MAX_SESSIONS`; stop a session (and its commentary stream) when the
   socket closes or the tab is hidden for more than 2 minutes (Page Visibility; the client closes the socket), so a forgotten tab
   does not call Foundry for 90 minutes.
3. Default start for a new listener: kick-off, but the client offers "30 s before the first goal" as a hint on the timeline, not
   as a button.

## 3. Highlights (~2 h)
1. Server: `mode=highlights`: the session plays, in order, each moment's window `[moment - 30 s, moment + 15 s]` (merge windows
   that overlap), warmed once per window and cached. Between windows send a `cut` message `{t_from, t_to}`; at the end of the
   first half and at full time insert the recap (Recap agent; cached full-time recap for seed 7).
2. Client: on `cut`, a short transition (soft whoosh, the minute shown "34'" and read in the status line), the timeline playhead
   jumps; score and stats come from the server's warm-up state, never recomputed in the client.
3. The live commentator works per window (each window is a stretch); the 20 s delay buffer is filled by the burst at each window
   start, as for jumps. Callouts and narration as in Live.
4. Report the length of Highlights for each listed match in STATUS (target 8-14 minutes; if a match is far longer, raise the
   bar for which moments count, e.g. leave out saved shots outside the box, and say so).

5. **Commentary cache key:** today the commentator's fallback cache is keyed by (seed, start minute, segment, prompt version,
   model). With any-minute starts and Highlights windows, that key fragments and the fallback almost never hits. Segments are
   deterministic over the whole match, so key by (match, segment id, prompt version, model) and drop the start minute; check
   segment ids do not depend on where the session started (test). Keep the files already cached by migrating or regenerating.

## 4. Matches and clubs (~2 h)
1. A small fictional league: **6 clubs**, approved by the owner (2026-10-23): **Northport** (red), **Valemont** (blue),
   **Kingsmoor** (yellow), **Lornbridge** (orange), **Zekteris** (white), **Thornfield** (purple). Same spelling in EN and
   TR. **Zekteris** is the owner's choice; keep it whatever the search says about other uses, and give it at least two matches in the fixture list. No green (the pitch is green). Check by
   web search that no professional club uses the other names; if one does, use a spare (Silverbay, grey; Corvale, black, but
   never against Valemont, the names are too close) and note it in STATUS. Do not use
   Eastbrook or Westmere (they are the prompt's example teams). In the fixture list, avoid pairs that look alike for colour-blind
   viewers (e.g. red v orange); keep a shape cue as today, not colour alone. Each club gets 11 fictional players (varied,
   plausible, no real footballers' names); Northport and Valemont keep their current squads.
2. `htg/league.py`: the clubs, squads and a fixture list of 5-6 matches: `{id, seed, home, away}`. Seed 7 = Northport v Valemont.
   Other seeds from **31 upwards** (1-10 are tuning seeds, 11-30 reporting seeds; do not use them). Pick seeds whose matches have
   at least one goal; picking interesting fixtures is fine, changing the data is not.
3. `generate(seed, home=, away=)` takes the clubs; names must not feed the RNG: extend the existing hash test so seed 7 events stay
   identical and seed 31 events are the same with two different club pairs.
4. Server serves the fixture list in `hello` (or `/matches.json`); matches are generated on first request (seconds, cached on disk
   in the container) and warmed in a thread; the Dockerfile may pre-generate them at build.
5. Callout clips for the new club names and surnames (both languages, both tones) with `python -m htg.speech.callouts`; check the
   size. Narration, recaps and commentary for new matches are generated live (cache fills as people listen).
6. Favourite club now picks from the six clubs; it applies to whichever match includes that club.

## 5. Docs and checks
- README: "Pick a match, watch live or as highlights" in What you hear / see; feed docs (`match`, `mode`, `from`, `cut`); fixture
  list; note that matches beyond the default are generated and voiced live. STATUS, including Highlights lengths and the live
  latency seen on a new match. Move this file to `docs/tasks/done/` when finished.
- Headless check: each match starts in Live and Highlights, no console errors, timeline click works, phone width has no
  horizontal scroll.

## Owner
Club names are approved (see part 4). After deploy: watch Highlights of the default match end
to end, start one other match live, and check the layout on the phone.

## Out of scope
Playback speed control, user accounts, real fixtures or real club data, a season table.
