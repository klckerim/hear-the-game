# 2026-10-24: evidence timeline, analyst panel (and optional MCP)

Context: the rules ask us to "explain why a moment matters" and to give the analyst and the casual fan "two genuinely different
experiences". Today the pitch shows one dot and the Analyst view adds three meters. This task makes the evidence behind every
Insight visible (the strongest proof of "explainable") and gives the analyst real numbers. Selection rule: only what a judge notices
in the video or the first minute of the demo. English first. Next comes the extra task (live commentator), so keep this one tight.
See "Scope and token budget" in CLAUDE.md. Do not refactor `web/live.html` into a framework; vanilla JS stays.

Done when:
- Under the pitch, a timeline of the session window with markers for goals, shots and Insights; selecting a marker highlights its
  evidence on the pitch and shows its facts.
- Analyst mode shows a team stats table (match / last 10 min) and richer event log lines (shot speed, pass length).
- `ruff check . && pytest` pass; deployed; owner checked it at desktop and phone width.
- **Cut order if time runs out:** MCP (part 3), then the analyst panel (part 2). The timeline (part 1) is the one to keep.

## 0. Housekeeping (5 min, first commit)
- STATUS: the owner deployed the language split and listened to EN page + TR commentary and the reverse (2026-10-22); close that item.
- `web/live.html` still has an unused `#timeline` CSS rule from Day 2 (no element). Reuse that id for the new timeline or delete it.
- The app now has a manifest and icons (PWA); do not break them.

## 1. Evidence timeline and pitch highlight (~4 h)
1. Server: the `insight` message gains `evidence_points`: for each evidence `seq` (cap 30), `{seq, t, type, team, x, y}` from the
   event's start position, in the same pitch orientation the client draws. Deterministic; schema/feed docs updated.
   `event_cue` today carries `t, kind, team, seq, period, player_id, pan` but no position: add `x, y` (start position) for shots
   and goals, and `speed_mps` where the event has it (needed for part 2).
2. Client, below the pitch (Casual and Analyst; hidden in Audio only): a horizontal strip for the session's 15 minutes with markers:
   goal (large, club colour + shape, not colour alone), shot (small), Insight (diamond; filled if it was spoken). A playhead moves with
   the match clock. Markers are buttons (keyboard and screen reader: label like "Insight, 21:40, Northport pressing").
3. Selecting a marker (click, Enter):
   - pitch: evidence points drawn as small dots for a few seconds, plus a zone shade by type: `flank_overload` -> that flank band
     (the y thresholds the detector uses, in the attacking frame), `pressure_shift` -> the pressed team's half, `physical_drop` ->
     the player's evidence points only, `tempo_change` -> no zone, the dots only, shot/goal -> the shot position and a line to goal;
   - a small "Why" card under the timeline: the sentence (commentary language, dual caption rules apply), `verified` / `template`
     tag, and the `claim_facts` as a compact key/value list (not raw JSON), plus "evidence: N events".
   The match keeps playing; the highlight fades after ~6 s or on the next selection.
4. New Insights flash their marker briefly when detected, so a sighted judge sees the system "noticing" something.
5. Tests: `evidence_points` match the events by seq and stay within the pitch; capped at 30.

## 2. Analyst panel (~3 h)
1. Server: every 10 s of match time, a `stats` message from `htg/recap/tools.get_stats` (reuse it; do not write a second
   implementation): match so far and last 10 minutes. Same deterministic numbers the recap agent sees.
2. Client (Analyst only): a two-column table, home vs away, with a "Match / Last 10 min" toggle: possession %, shots (on target),
   pass completion %, pressing %, corners, fouls. Small horizontal bars per row; numbers as text.
3. Event log lines (Analyst): shots with speed in km/h from `speed_mps` and the outcome ("Shot · Okafor · 87 km/h · saved"); passes
   are not all logged, but long passes (> 30 m) show their length. Use the event fields that exist; do not invent a "difficulty"
   score.
4. Fan modes stay simple: no table.

## 3. Optional, only if parts 1-2 are done and deployed: MCP server (~1 h, timebox)
`python -m htg.mcp` (stdio, official Python MCP SDK): read-only tools wrapping `htg/recap/tools.py` (`get_score`, `get_stats`,
`get_insights`, `get_player`) for a given seed and minute. Add `.vscode/mcp.json` so GitHub Copilot agent mode in VS Code can ask
"Who pressed harder after minute 60 in match 7?". One test that the tools list and one call work. README: two lines on how to use
it. If it does not work within the hour, drop it.

## 4. Docs
README: "Evidence timeline" and "Analyst view" lines in "What you hear / see", feed docs (`evidence_points`, `stats`), screenshots
placeholder. STATUS. Move this file to `docs/tasks/done/` when finished.

## Owner
Check the timeline and the Why card at 1280 px and phone width; click three Insights and one goal; switch to Analyst and back.

## Out of scope
Live commentator, callouts, cards, next-moment button (extra task), new detectors, generator changes.
