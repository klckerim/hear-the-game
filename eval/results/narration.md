# Narration evaluation

Seeds 11-30 (reporting seeds), mode `casual`, 100 spoken Insights sampled evenly.

## Live model and voice (100 Insights, model `foundry:gpt-5-mini`, reasoning effort `minimal`, prompt v3, 2026-10-21)

| | EN | TR |
|---|---|---|
| first-pass Verifier rate | 100% | 100% |
| template fallback rate (after one retry) | 0% | 0% |

- Narration latency per Insight, EN+TR in one call incl. retries (p50 / p95): 1.54 s / 2.89 s
- TTS latency per clip (p50 / p95): 0.47 s / 0.89 s over 200 clips
- Model tokens: 67616; characters sent to TTS: 12620

### Latency before and after (all measured, same seeds and model)

| date | prompt | reasoning effort | Insights | narration p50 / p95 | first-pass EN / TR |
|---|---|---|---|---|---|
| 2026-10-21 | 1 | default | 100 | 10.73 s / 17.42 s | 100% / 100% |
| 2026-10-21 | 1 | minimal | 30 | 1.87 s / 4.90 s | 93% / 93% |
| 2026-10-21 | 2 | default | 100 | 7.71 s / 17.51 s | 100% / 100% |
| 2026-10-21 | 2 | minimal | 100 | 1.58 s / 2.79 s | 100% / 100% |
| 2026-10-21 | 3 | minimal | 100 | 1.54 s / 2.89 s | 100% / 100% |

Reading the prompt-2 samples ([narration_samples_prompt2.jsonl](narration_samples_prompt2.jsonl)) by hand found what
the Verifier then missed: 13 of 200 accepted sentences read out a code value (`off_target`), some invented shot locations
("from the edge"), and one goal sentence on the demo match credited the score to the wrong team.
Fixes: a Verifier rule for code values, prompt 3 (say only what the facts say), and goal facts
without the opponent's name, so naming the wrong team fails the name check.
Invented details without a number or a name are still not caught deterministically.

## Real catches (model errors the Verifier stopped)

Unlike the mutation test below, these are drafts the model actually wrote on reporting seeds. A rejected sentence is never
spoken: the model gets the reasons for one retry, then the template sentence is used.

Rejected first drafts: 0 of 200 sentences (EN 0, TR 0); rejected retries: 0.

## Verifier mutation test (no Azure)

Template sentences with one injected error. **The mutations are synthetic**: they show the checks fire,
not how often a model errs.

| mutation | sentences | caught |
|---|---|---|
| added cause | 200 | 100% |
| changed number | 90 | 100% |
| swapped player | 146 | 100% |
| **all** | 436 | 100% |

Unmutated template sentences accepted: 200 of 200 (must be all).
