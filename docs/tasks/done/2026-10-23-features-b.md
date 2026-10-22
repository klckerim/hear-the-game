# 2026-10-23: sound tour and Recap agent

Context: rules ask for "automated match recaps suitable for studio, broadcast, or streaming" (named three times) and score
"Agentic Design & Innovation" at 20%; we have neither a real recap nor an agent. Judges also do not know what the sounds mean, so
the demo needs a short guided tour. Category stays **Best Use of Microsoft Foundry**. Selection rule: if a judge would not notice it
in the video or the first minute of the demo, do not build it. See "Scope and token budget" in CLAUDE.md.

Done when:
- Before the first start, the listener is offered a 45-60 s sound tour (skippable, remembered); captions TR/EN.
- "What did I miss?" produces a 2-3 sentence recap written by a Foundry agent that calls deterministic tools; perspective of the
  favourite club; fan or analyst persona; every sentence passes the Verifier, otherwise the old behaviour (score + last 3 narrations).
- A full-time recap is spoken at the end of the `late` chapter.
- `eval/results/recap.md` exists with real numbers.
- `ruff check . && pytest` pass without Azure; deployed with `azd deploy`; owner listened.
- **Cut-off 20:00:** if the agent does not work reliably by then, keep the tour, revert "What did I miss?" to the old behaviour and stop.

## 1. Sound tour (client, ~3 h)
1. A "New here? 60-second sound tour" button next to "Start listening", shown until the tour is done or skipped (`localStorage`, try/catch).
2. Steps, each plays the real sound through the existing audio functions, with a one-line caption and a short voice line:
   ball tick low -> high (danger) · left -> right (wing) · the two team timbres · heartbeat (pressure) · crowd follows danger ·
   pass click, shot whoosh, save thud, whistle · goal figure for your club vs against · favourite-player chime · narration ducks the sound.
3. Voice lines: pre-generated Azure clips (same voices as narration, EN + TR, about 10 lines each), committed under `data/cache/tour/`.
   Text in one table so captions and audio match. "Skip" stops at once and starts nothing.
4. Captions in an `aria-live` region; the tour must not start the match.

## 2. Recap tools (deterministic, ~2 h)
`htg/recap/tools.py`, pure functions over the replay **up to time `t`** (never after `t`, never `truth.json`):
- `get_score(t)` -> score, minute, period.
- `get_stats(t, from_min, to_min)` -> per team: possession share, shots, shots on target, pass completion, pressure share, corners, fouls.
- `get_insights(t, from_min, to_min)` -> the Insights detected in that window (type, team, player, claim_facts, minute).
- `get_player(t, player_id, from_min, to_min)` -> touches, passes, shots, high-speed running vs his earlier level.
Every returned number is rounded the way it may be spoken. Tests: no data after `t` leaks (feed a `t` before the first goal, score is 0-0);
same inputs, same output.

## 3. Recap agent on Foundry (~4 h)
1. Look up the current Foundry agent API with the `microsoft-learn` MCP first (Foundry Agent Service / prompt agents with function
   tools, Responses API in `azure-ai-projects`). The API moved recently; do not write it from memory. Timebox 90 min. Fallback: a
   function-calling loop on the existing OpenAI client against the same deployment (still an agent that chooses its tools; say which
   one was built in README and STATUS).
2. Input: `t`, `since_min` (what the listener missed; default last 10 minutes, full match for full time), favourite club or none,
   persona, language pair. Instructions: call tools, at most 4 calls; then 2-3 sentences per language, radio tone; perspective "your
   team" when a favourite club is set; only facts from tool results; no causes, no injuries.
   Output JSON: `{"en": [...], "tr": [...], "tools_used": [...]}`.
3. Verifier: each sentence checked with the existing rules; known facts = all values returned by the tools in this run, known names =
   the match's clubs and players. A failing sentence is dropped; if no sentence survives in a language, use the template recap for it.
4. Speech: same voices; play like a narration (ducking). The "What did I miss?" button shows "Preparing..." while it runs.
5. Full time: at `period_end` of period 2 in the `late` chapter, the server requests a full-time recap and sends it as `recap`.
   Pregen the full-time recap for each favourite club x persona x language so the demo does not wait.
6. Telemetry: one span per recap with tool calls, verifier result and source (agent / template); the model calls nest under it.
7. Tests (fake model, no network): tool-call loop stops at 4; a sentence with a number not in tool results is dropped; template fallback.

## 4. Recap eval
`eval/recap.py --seeds 11-30 --n 20`: random `t` in the second half, random favourite. Report: sentences passing the Verifier
(EN, TR), fallback rate, tool calls per recap, latency p50/p95. Read 5 recaps yourself and quote 2 verbatim (EN + TR) in
`eval/results/recap.md`; list any invented detail you find (do not hide it).

## 5. Docs
README: "Recap agent" section (tools, Verifier, fallback, numbers from `recap.md`), Microsoft stack row, Mermaid diagram node.
STATUS: what was built (agent service or fallback loop), open items. Move this file to `docs/tasks/done/` when finished.

## Owner
- Listen to the tour in TR and EN; check it is clear without explanation.
- Click "What did I miss?" at three moments in each chapter; listen to the full-time recap.
- Decide: should a `half_time` chapter (around 41') be added so the demo can show a half-time studio recap? Default: no.

## Out of scope
Live commentator, callouts, cards, highlight jumps (separate task), insight timeline, analyst panel, MCP.
