# 2026-10-25: re-run the Foundry evaluation on the shipping prompt (small)

Context: `eval/results/foundry_eval.md` is from 2026-10-21: prompt 3, the old team names ("the Reds"), and its note says
"Prompt 4 (shipping)", which is no longer true (prompt 5 with fan / analyst personas ships). Samples with the current prompt and club names already exist and need no new model calls:
`eval/results/narration_samples_prompt5_fan.jsonl` and `..._analyst.jsonl` (50 Insights each, seeds 11-30, Northport / Valemont).

## Token budget (strict)
No screenshots, no image reads. Short command output. No new narration generation. `ruff check . && pytest` once before the commit.

## 1. Run
1. Check that `eval/foundry_eval.py` still builds its groundedness context correctly with the prompt-5 `SYSTEM`
   (`FACT_MEANINGS` slices `SYSTEM` between "Fact meanings:" and "The example shows"; if prompt 5 moved or renamed these, fix the
   slice so the context is the fact meanings the narrator saw, nothing else). Print the first row's context length and first 200
   characters to confirm.
2. One run per persona (two Foundry runs, separate names so both show in the portal):
   `python -m eval.foundry_eval --samples eval/results/narration_samples_prompt5_fan.jsonl --out <tmp>` and the same for analyst.
   If the script cannot name runs, add an optional `--name` (default as today).

## 2. Results file
Rewrite `eval/results/foundry_eval.md` with the date, prompt 5, the two runs (portal links), one table per persona (same columns as
today), and a short reading note (what fluency 3 reasons cite, as before; only what the results say). Keep the 2026-10-21 prompt-3
run as a dated history row with its numbers and link. Remove the "Prompt 4 (shipping)" sentence.

## 3. README and STATUS
Update the Foundry evaluation numbers in README (grep `4.99` and `fluency`) to the new runs, stating n and persona. STATUS: one
line under the newest section. If a number got worse, write it as it is.

## Owner (not Claude Code)
No deploy needed (eval only).

## Out of scope
Commentator lines in the Foundry evaluation (possible later, separate task), prompt changes, new samples.
