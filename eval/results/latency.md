# Deployed latency

Measured from outside with `python -m eval.latency` (see the module docstring). What this does **not** measure:

- Client audio latency (Web Audio scheduling, Bluetooth headphones). The client also adds a fixed 300 ms jitter buffer on purpose.
- Cache hit vs live model call: the `speech` message only says `llm` (verified) or `template`. The split is in the App Insights
  metric `htg.speech.resolved` (source cache / llm / template).
- Speech dropped as stale (resolved more than 8 s of match time late) never reaches the client; it is counted only in the
  App Insights metric `htg.speech.dropped_stale`.

### 2026-10-21: 1 session(s), 3 min, mode `casual`

Client: Istanbul -> Sweden Central. URL `wss://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/ws`. Sessions started together; each replays the demo match from minute 13.

| measure | n | p50 / p95 / max |
|---|---|---|
| connect -> `hello` | 1 | 1540 / 1540 / 1540 ms |
| `state` inter-arrival (nominal 200 ms) | 891 | 200 / 214 / 783 ms |
| decision -> `speech` (server resolve, approx. +/- one state batch) | 2 | 224 / 224 / 224 ms |
| `insight` -> `speech` (incl. Director hold) | 2 | 284 / 284 / 284 ms |

- `speech` EN by source: llm 2 (100%); with audio: 2 of 2
- `speech` TR by source: llm 2 (100%); with audio: 2 of 2
- Session errors: 0

### 2026-10-21: 10 session(s), 3 min, mode `casual`

Client: Istanbul -> Sweden Central. URL `wss://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/ws`. Sessions started together; each replays the demo match from minute 13.

| measure | n | p50 / p95 / max |
|---|---|---|
| connect -> `hello` | 10 | 12862 / 15289 / 15289 ms |
| `state` inter-arrival (nominal 200 ms) | 8348 | 199 / 272 / 15801 ms |
| decision -> `speech` (server resolve, approx. +/- one state batch) | 20 | 985 / 15643 / 15643 ms |
| `insight` -> `speech` (incl. Director hold) | 20 | 1047 / 15659 / 15659 ms |

- `speech` EN by source: llm 20 (100%); with audio: 20 of 20
- `speech` TR by source: llm 20 (100%); with audio: 20 of 20
- Session errors: 0

**Finding (fixed after this run):** every listener ran its own 13-minute warm-up; 10 at once starved the server's event loop, so
`hello` took ~13 s and running sessions saw a 15.8 s stall. The server now warms up once and gives each session a copy
(`services/engine/serve.py`, `warmed`). Same 10-session test against a local server: `hello` p50 2218 -> 597 ms. Re-measured
on the deployed app below once redeployed.

### 2026-10-21: 1 session(s), 3 min, mode `analyst`

Client: Istanbul -> Sweden Central. URL `wss://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/ws`. Sessions started together; each replays the demo match from minute 13.

| measure | n | p50 / p95 / max |
|---|---|---|
| connect -> `hello` | 1 | 1093 / 1093 / 1093 ms |
| `state` inter-arrival (nominal 200 ms) | 893 | 200 / 327 / 2063 ms |
| decision -> `speech` (server resolve, approx. +/- one state batch) | 2 | 628 / 628 / 628 ms |
| `insight` -> `speech` (incl. Director hold) | 2 | 697 / 697 / 697 ms |

- `speech` EN by source: llm 2 (100%); with audio: 2 of 2
- `speech` TR by source: llm 2 (100%); with audio: 2 of 2
- Session errors: 0

### 2026-10-21: 10 session(s), 3 min, mode `casual`

Client: Istanbul -> Sweden Central. URL `wss://ca-engine.proudflower-32a91b05.swedencentral.azurecontainerapps.io/ws`. Sessions started together; each replays the demo match from minute 13.

| measure | n | p50 / p95 / max |
|---|---|---|
| connect -> `hello` | 10 | 3789 / 6506 / 6506 ms |
| `state` inter-arrival (nominal 200 ms) | 8809 | 200 / 237 / 3421 ms |
| decision -> `speech` (server resolve, approx. +/- one state batch) | 20 | 1436 / 3421 / 3421 ms |
| `insight` -> `speech` (incl. Director hold) | 20 | 1559 / 3476 / 3476 ms |

- `speech` EN by source: llm 20 (100%); with audio: 20 of 20
- `speech` TR by source: llm 20 (100%); with audio: 20 of 20
- Session errors: 0

After the warm-up fix (redeployed 2026-10-21), same test: `hello` p50 12.9 s -> 3.8 s, longest `state` gap 15.8 s -> 3.4 s,
speech p95 15.6 s -> 3.4 s. The container has 0.5 vCPU and every session runs its own state engine and detectors in real time;
the remaining delay when 10 listeners start in the same second is most likely CPU contention (not measured separately).
