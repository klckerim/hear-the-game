# Recap agent: 2026-10-22

`HTG_ENV=azure python -m eval.recap --seeds 11-30 --n 20` (reporting seeds only). Model `gpt-5-mini` (reasoning effort `minimal`) as a Foundry Agent Service prompt agent with 4 function tools, recap prompt v6. Random moment in the second half, random favourite club (or none) and persona; the listener missed the last 10 minutes. No cache, no TTS.

| Measure | EN | TR |
|---|---|---|
| Sentences passing the Verifier, first draft | 95% (57/60) | 83% (50/60) |
| ... after the one revision | 98% (59/60) | 88% (53/60) |
| Template fallback (recap level) | 0% | 0% |

- Recaps: 20; model errors: 0; revisions asked: 6.
- Tool calls per recap: mean 2.0, max 2 (limit 4). Tools used: get_score 20, get_stats 20.
- Latency (agent turns + tools + Verifier, no TTS): p50 6.06 s / p95 13.08 s.
- A fallback language gets the deterministic template recap (score, the spell's possession and shots, the latest goal).

All recaps: [recap_samples.jsonl](recap_samples.jsonl).
## History (same command, seeds 11-30, n 20)

| Date | Prompt | Change before the run | First draft EN / TR | After revision EN / TR | p50 / p95 |
|---|---|---|---|---|---|
| 2026-10-22 | v4 | first version with a revision turn | 100% / 58% | 100% / 67% | 9.16 s / 11.50 s |
| 2026-10-22 | v6 | Turkish rewrite examples (tuned on seeds 1-10: 100% / 100% there) | 100% / 92% | 100% / 93% | 5.97 s / 9.39 s |
| 2026-10-22 | v6 | wider Turkish suffix rule; `to_min` at the current minute means "now" | 95% / 83% | 98% / 88% | 6.06 s / 13.08 s |

The last row is the table above. Between the v6 rows the prompt did not change; the Verifier got stricter (below) and run-to-run
variation of the model is visible: 20 recaps are a small sample.

## Reading (by hand, last run)

Read 5 recaps of the last run (rows 0, 6, 12, 15, 18) and 7 of the previous run, and checked every number against the tools
with the agent's own window. All numbers matched their tool result. Two verbatim from the last run:

- Row 6 (seed 26, minute 70, favourite Northport, analyst). EN: "It is Northport 0, Valemont 1; your team are behind. Since minute
  60 Valemont had 67% of the ball and Northport 33% of the ball. Since minute 60 both teams had 1 shot; Valemont had 1 on target while
  Northport had 0 on target." TR: "Skor Northport 0, Valemont 1; takımın geride. Dakika 60 sonrası Valemont topun yüzde 67 kadarı
  onlarda, Northport topun yüzde 33 kadarı onlarda. Dakika 60 sonrası her iki takım da 1 şut çekti; Valemont 1 isabetli şut var,
  Northport 0 isabetli şut var."
- Row 18 (seed 29, minute 56, no favourite, fan). EN: "The score is Northport 1, Valemont 1 at minute 56. Since minute 46 Valemont
  have had more of the ball and more shots. Northport have managed 1 shot on target and 3 fouls in that period." TR: "Skor Northport
  1, Valemont 1, dakika 56. Dakika 46 sonrası Valemont topun daha fazlasına sahip ve daha çok şut attı. Northport o sürede 1 isabetli
  şut attı ve 3 faul yaptı."

Problems found by reading (not by the Verifier):

- **Turkish suffix written apart from the number** ("3 ü isabetli", "1 i isabetli", "yüzde 37 si"): 4 of 56 accepted Turkish
  sentences in the previous run. The voice reads the suffix as a separate word. Fixed after reading: the Verifier now also rejects a
  suffix word after a number (`TR_SPLIT_SUFFIX`); the last run has 0 in shipped sentences, and its stricter rejections are part of
  the lower Turkish first-draft rate.
- **Invented stats in tool arguments:** in row 18 the model passed made-up possession and shot numbers as extra arguments to
  `get_stats`. The tool ignores unknown arguments and the Verifier only accepts values the tools returned, so none of these reached a
  sentence (checked), but it shows why facts must come from tool output, not from the model's own calls.
- **A stale window:** before the `to_min` fix the agent asked "minute 60 to 70" at 70:38 and missed a shot in the last 38 s (true
  for its window, wrong for the listener). Fixed in the tool.
- **Wording:** "81 yüzde" (word order) in one Turkish sentence; the fan persona still uses more numbers than asked; the full-time
  recap once said "Tam zaman" (a calque of "full time") in Turkish ([recap_fulltime.md](recap_fulltime.md)).
- **Vague claims:** an earlier run said "Valemont have had 55% of the ball and more of the play": "more of the play" is not
  measured by any tool. A rejected (never shipped) Turkish draft said "gol geçerli" ("the goal stands"), which no tool says. The
  Verifier checks numbers, names and words; it cannot catch an unmeasured claim without a number or a name, and it cannot tell
  whether a number that is in the tool results sits next to the right label.
