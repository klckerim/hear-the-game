# Narration evaluation

Seeds 11-30 (reporting seeds), mode `casual`, 100 spoken Insights sampled evenly.

## Live model and voice (100 Insights, model `foundry:gpt-5-mini`)

| | EN | TR |
|---|---|---|
| first-pass Verifier rate | 100% | 100% |
| template fallback rate (after one retry) | 0% | 0% |

- Narration latency per Insight, EN+TR in one call incl. retries (p50 / p95): 10.73 s / 17.42 s
- TTS latency per clip (p50 / p95): 0.40 s / 1.44 s over 200 clips
- Model tokens: 148814; characters sent to TTS: 12960

## Verifier mutation test (no Azure)

Template sentences with one injected error. **The mutations are synthetic**: they show the checks fire,
not how often a model errs.

| mutation | sentences | caught |
|---|---|---|
| added cause | 200 | 100% |
| changed number | 90 | 100% |
| swapped player | 90 | 100% |
| **all** | 380 | 100% |

Unmutated template sentences accepted: 200 of 200 (must be all).
