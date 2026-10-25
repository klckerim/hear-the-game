# Foundry evaluation of the narration

2026-10-25. Prompt 5 (the shipping prompt, with fan and analyst personas). 50 Insights per persona from
[narration_samples_prompt5_fan.jsonl](narration_samples_prompt5_fan.jsonl) and
[narration_samples_prompt5_analyst.jsonl](narration_samples_prompt5_analyst.jsonl) (seeds 11-30, clubs Northport / Valemont, the
sentences that ship: model text that passed the Verifier). Built-in evaluators `builtin.groundedness` and `builtin.fluency`
(1-5, pass threshold 3), judge `gpt-5-mini`. Groundedness context = the Insight's claim_facts plus what each key means, as the
narrator saw them (the persona block is not in the context). Rows without a numeric score (judge errors): 0 in both runs.

## Fan persona

Foundry run `narration-prompt5-fan-2026-10-25`: `evalrun_78f49e907b854671b45d7306a087a3c1` (eval `eval_f418e5fe0eec4ee683191d366623496e`).
Portal: https://ai.azure.com/nextgen/r/LEIDGpBYStWgkYX9XBMwXQ,hear-the-game,,hearthegame,hearthegame/build/evaluations/eval_f418e5fe0eec4ee683191d366623496e/run/evalrun_78f49e907b854671b45d7306a087a3c1
Per-row scores and reasons: [foundry_eval_prompt5_fan_items.jsonl](foundry_eval_prompt5_fan_items.jsonl).

| evaluator | lang | n | mean | 1 | 2 | 3 | 4 | 5 | pass (>=3) |
|---|---|---|---|---|---|---|---|---|---|
| groundedness | EN | 50 | 4.72 | 0 | 0 | 0 | 14 | 36 | 100% |
| groundedness | TR | 50 | 4.66 | 0 | 1 | 0 | 14 | 35 | 98% |
| fluency | EN | 50 | 3.08 | 0 | 0 | 46 | 4 | 0 | 100% |
| fluency | TR | 50 | 3.28 | 0 | 0 | 36 | 14 | 0 | 100% |

## Analyst persona

Foundry run `narration-prompt5-analyst-2026-10-25`: `evalrun_c6ec4d75b565450dafd2048701fc1204` (eval `eval_126abdea001f45059721acb5e01cb440`).
Portal: https://ai.azure.com/nextgen/r/LEIDGpBYStWgkYX9XBMwXQ,hear-the-game,,hearthegame,hearthegame/build/evaluations/eval_126abdea001f45059721acb5e01cb440/run/evalrun_c6ec4d75b565450dafd2048701fc1204
Per-row scores and reasons: [foundry_eval_prompt5_analyst_items.jsonl](foundry_eval_prompt5_analyst_items.jsonl).

| evaluator | lang | n | mean | 1 | 2 | 3 | 4 | 5 | pass (>=3) |
|---|---|---|---|---|---|---|---|---|---|
| groundedness | EN | 50 | 4.92 | 0 | 1 | 0 | 1 | 48 | 98% |
| groundedness | TR | 50 | 4.92 | 0 | 1 | 0 | 1 | 48 | 98% |
| fluency | EN | 50 | 3.14 | 0 | 0 | 43 | 7 | 0 | 100% |
| fluency | TR | 50 | 3.40 | 0 | 0 | 30 | 20 | 0 | 100% |

## Reading

Groundedness is lower than the prompt-3 run (4.99). Of the 29 fan rows below 5, 23 are chances written as two exclamations
("Chance for Valemont! Okafor shoots and the keeper saves."): the reasons say the facts are correct but the query asked for one
sentence. 5 more are fan lines without numbers (the fan persona is told to prefer none); the reasons call them correct but
incomplete. The three rows scored 2:
- Fan TR flank overload, "Valemont önceden olduğu kadar değil, şimdi ısrarla sağ kanattan oynuyor": the share went from 23% to 47%,
  and "önceden olduğu kadar değil" can be read as a decrease. A real wording problem the Verifier cannot see (no number or name is wrong).
- Analyst EN chance, "... is off target and misses the keeper": "misses the keeper" is a detail the facts do not give. Real, minor.
- Analyst TR pressure shift, "son 5 dakikada ... yüzde 54, maçın önceki bölümünde yüzde 32": the judge read the rule about
  `*_before` as banning "in the last 5 minutes" for `*_now`. The sentence follows the fact meanings; this is a judge error.

Fluency: no sentence scored below 3. 78 of the 82 fan reasons for a 3 and 69 of the 73 analyst ones cite brevity or simplicity.
The rubric rewards complex sentences; the narrator is told to say one short radio sentence, so 3-4 is the expected range.

Caveats: the judge is the same model family that wrote the sentences; an LLM judge on Turkish is weaker evidence than
on English. The deterministic Verifier (see [narration.md](narration.md)) is the guarantee; this is a second opinion.

## History

| date | prompt | samples | groundedness EN / TR | fluency EN / TR | run |
|---|---|---|---|---|---|
| 2026-10-21 | 3 (old team names) | 100 Insights, [narration_samples_prompt3.jsonl](narration_samples_prompt3.jsonl) | 4.99 / 4.99 | 3.13 / 3.48 | `evalrun_d1e544f071134e49b9cd4e97c3efac09`, [portal](https://ai.azure.com/nextgen/r/LEIDGpBYStWgkYX9XBMwXQ,hear-the-game,,hearthegame,hearthegame/build/evaluations/eval_a693656d65f94bc6a057dff3657fa2f0/run/evalrun_d1e544f071134e49b9cd4e97c3efac09), [items](foundry_eval_prompt3_items.jsonl) |
