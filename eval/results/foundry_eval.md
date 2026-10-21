# Foundry evaluation of the narration

2026-10-21. 100 Insights from [narration_samples_prompt3.jsonl](narration_samples_prompt3.jsonl) (prompt 3, seeds 11-30, the sentences that ship: model text that passed the
Verifier). Built-in evaluators `builtin.groundedness` and `builtin.fluency` (1-5, pass threshold 3), judge `gpt-5-mini`.
Groundedness context = the Insight's claim_facts plus what each key means, as the narrator saw them.
Evaluated on prompt-3 sentences. Prompt 4 (shipping) changed only how Turkish attaches suffixes to numbers; not re-evaluated.

Foundry run: `evalrun_d1e544f071134e49b9cd4e97c3efac09` (eval `eval_a693656d65f94bc6a057dff3657fa2f0`). Portal: https://ai.azure.com/nextgen/r/LEIDGpBYStWgkYX9XBMwXQ,hear-the-game,,hearthegame,hearthegame/build/evaluations/eval_a693656d65f94bc6a057dff3657fa2f0/run/evalrun_d1e544f071134e49b9cd4e97c3efac09

| evaluator | lang | n | mean | 1 | 2 | 3 | 4 | 5 | pass (>=3) |
|---|---|---|---|---|---|---|---|---|---|
| groundedness | EN | 100 | 4.99 | 0 | 0 | 0 | 1 | 99 | 100% |
| groundedness | TR | 100 | 4.99 | 0 | 0 | 0 | 1 | 99 | 100% |
| fluency | EN | 100 | 3.13 | 0 | 0 | 87 | 13 | 0 | 100% |
| fluency | TR | 100 | 3.48 | 0 | 0 | 52 | 48 | 0 | 100% |

Rows without a numeric score (judge errors): 0.

Reading fluency: no sentence scored below 3; 136 of the 139 reasons for a 3 cite brevity or simplicity:
correct and clear, but "brief and simple, lacking complex sentence structures or varied vocabulary" (per-row reasons in
[foundry_eval_items.jsonl](foundry_eval_items.jsonl)). The rubric rewards complexity; the narrator is told to say one
short radio sentence, so 3-4 is the expected range, not a quality problem.

Caveats: the judge is the same model family that wrote the sentences; an LLM judge on Turkish is weaker evidence than
on English. The deterministic Verifier (see [narration.md](narration.md)) is the guarantee; this is a second opinion.
