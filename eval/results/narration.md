# Narration evaluation

Seeds 11-30 (reporting seeds), mode `casual`, 100 spoken Insights sampled evenly.

## Personas: fan vs analyst (prompt 5, 2026-10-22)

Casual and Audio only narrate as a **fan** (radio excitement, at most one number, at most 16 words); Analyst narrates as an
**analyst** (the key numbers and the comparison, at most 25 words). Same Verifier and same template fallback for both.
50 spoken Insights (seeds 11-30, the same Insights for both personas), gpt-5-mini, reasoning effort `minimal`, no cache.
`python -m eval.narration --limit 50 --persona fan|analyst`. Samples:
[narration_samples_prompt5_fan.jsonl](narration_samples_prompt5_fan.jsonl),
[narration_samples_prompt5_analyst.jsonl](narration_samples_prompt5_analyst.jsonl).

| persona | first pass EN / TR | fallback EN / TR | narration p50 / p95 | mean numbers per sentence EN / TR | mean words EN / TR |
|---|---|---|---|---|---|
| fan | 100% / 96% | 0% / 0% | 1.71 s / 3.31 s | 0.30 / 0.32 | 11.3 / 8.5 |
| analyst | 98% / 100% | 0% / 0% | 1.84 s / 3.47 s | 1.08 / 1.08 | 13.7 / 10.8 |

Many sampled Insights are shots and goals, which carry no comparison numbers in either persona, so the analyst mean is near 1.

What we found on the way (all fixed before the numbers above):
- **Azure content filter.** The first fan run lost 3 of 50 pressing Insights to `content_filter` (HTTP 400 on the prompt). The
  hand-written fan example said "the Greens are pressing ... the Whites are feeling it": colour-named fixture teams. The fixture
  now uses club names (Eastbrook, Westmere). Rerun: 0 model errors.
- **Real Verifier catches.** 2 fan TR first drafts and 1 analyst EN draft were rejected; each retry passed. Two put a suffix on a
  number ("yüzde 15'e kıyasla"); in an earlier fan run one such draft also had the numbers in the wrong order ("yüzde 47'den
  yüzde 23'e artış"), stopped by the suffix rule, not by meaning. The analyst draft read out `off_target`.
- **Found by reading, not by the Verifier.** Fan drafts exaggerated ("hammering", "massively") or claimed more than the fact
  ("piling pressure on Valemont" for a flank overload, which measures where passes go). The fan block now asks for proportionate
  words and says what each fact measures. Some invented colour remains (e.g. "after a quiet spell"); it has no number or name,
  so the Verifier cannot catch it.
- **Demo cache.** After the seed-7 pregen, 3 of 36 demo sentences were regenerated after reading them (a Turkish "holding the
  ball in their hands", a broken English phrase, a doubled "kadarı kadar"); all three replacements are model text that passed
  the Verifier. Every demo sentence is listed in [demo_sentences.md](demo_sentences.md).

Earlier runs below used prompt 4 (one tone for everyone) and the old team names.

## Live model and voice (100 Insights, model `foundry:gpt-5-mini`, reasoning effort `minimal`, prompt v4, 2026-10-22)

| | EN | TR |
|---|---|---|
| first-pass Verifier rate | 100% | 100% |
| template fallback rate (after one retry) | 0% | 0% |

- Narration latency per Insight, EN+TR in one call incl. retries (p50 / p95): 1.58 s / 3.60 s
- TTS latency per clip (p50 / p95): 0.56 s / 2.13 s over 200 clips
- Model tokens: 70653; characters sent to TTS: 12420

### Latency before and after (all measured, same seeds and model)

| date | prompt | reasoning effort | Insights | narration p50 / p95 | first-pass EN / TR |
|---|---|---|---|---|---|
| 2026-10-21 | 1 | default | 100 | 10.73 s / 17.42 s | 100% / 100% |
| 2026-10-21 | 1 | minimal | 30 | 1.87 s / 4.90 s | 93% / 93% |
| 2026-10-21 | 2 | default | 100 | 7.71 s / 17.51 s | 100% / 100% |
| 2026-10-21 | 2 | minimal | 100 | 1.58 s / 2.79 s | 100% / 100% |
| 2026-10-21 | 3 | minimal | 100 | 1.54 s / 2.89 s | 100% / 100% |
| 2026-10-22 | 4 | minimal | 100 | 1.58 s / 3.60 s | 100% / 100% |

Reading the prompt-2 samples ([narration_samples_prompt2.jsonl](narration_samples_prompt2.jsonl)) by hand found what
the Verifier then missed: 13 of 200 accepted sentences read out a code value (`off_target`), some invented shot locations
("from the edge"), and one goal sentence on the demo match credited the score to the wrong team.
Fixes: a Verifier rule for code values, prompt 3 (say only what the facts say), and goal facts
without the opponent's name, so naming the wrong team fails the name check.
Invented details without a number or a name are still not caught deterministically.
Listening to the demo clips then found two Turkish voice problems: a suffix on a number ("36'ydı") was spelled out, and a
number before a full stop ("yüzde 23.") was read as an ordinal. Prompt 4 and a Verifier rule forbid number suffixes in
Turkish; the speech layer now says Turkish integers from words (`htg/speech/azure.py`).
Prompt-3 samples: [narration_samples_prompt3.jsonl](narration_samples_prompt3.jsonl) (used by the Foundry evaluation).

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
