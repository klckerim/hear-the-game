# Hear the Game

Microsoft × Premier League "Inside the Game" hackathon entry. Synthetic football events become spatial sound
(synthesized on the listener's device) and short, verified, multi-language narration (Microsoft Foundry + Azure AI
Speech). Target users: blind and partially sighted fans, and anyone who can't look at a screen.

Deadline: submission 2026-10-27 23:59 PT (2026-10-28 09:59 Istanbul). Plan to submit on 2026-10-27.
Read first: `docs/STATUS.md` (where we are, decisions, next steps). Design: `README.md` (architecture) and the code.
Current task: the newest file in `docs/tasks/` (finished ones are in docs/tasks/done/).

## Priority order (when in doubt, top wins)
1. A working end-to-end demo that never crashes: replay → sound → verified narration, in a good-looking UI.
2. Honest, measured claims (detector scores, latency, verifier catch rate).
3. Real Microsoft usage where it earns its place (Foundry, Speech, Container Apps, App Insights).
4. Everything else is optional. Cut it rather than half-build it.

## Scope and token budget (the owner is solo and cost-conscious)
- Keep it simple. No framework, abstraction or service that the demo does not need. Prefer 50 boring lines to a clever design.
- UI: single-page app, vanilla JS + CSS (no build step unless there is a clear need). Polish it visually; it is half the jury impression.
- Do not read big files. Never `cat` `ball.parquet`, `events.jsonl` or `calibration.json`; use `head`, `jq` or a short script and print a summary.
- Run narrow tests while working (`pytest tests/test_x.py -k name`); run the full suite once before each commit.
- One task per session. Finish a PR, commit, then `/clear` before the next one. Do not re-plan work that `docs/tasks/` already specifies.
- Use cheap, deterministic code first. LLM calls only for wording, small model, one call per insight, cached by insight fingerprint.
  The demo match narration is pre-generated and cached (text + audio clips) so the demo never depends on live model latency.
- If a step is slow or fiddly to automate (video recording, logo assets, screenshots, portal clicks, MCP setup), say so and leave it to the owner.
- Adapters: only the ones actually used (`EventSource`, `Broadcaster`, `Speech`). Add `Store`/`BlobStore` only when a feature needs them.
- Not building: Event Hubs, Cosmos DB, Web PubSub, Vite/TypeScript client, Agent Framework orchestration beyond what Foundry gives directly.
  README may describe them as the production path, clearly labeled "not built".

## Non-negotiable rules
1. Numbers come from code, words from the LLM. xT, pressure, durations, scores are computed deterministically.
   The LLM only turns given facts (`claim_facts`) into sentences.
2. No sentence ships without evidence. Every Insight carries the event `seq` numbers it rests on. The Verifier
   rejects any sentence whose numbers or names are not in `claim_facts`; on rejection, fall back to the template sentence.
3. Sound never waits for the LLM. The fast path (state → sound) and the slow path (insight → narration) are
   independent; if narration fails, sound continues.
4. The server sends data, the device makes the sound. Speech clips are the only audio sent over the wire.
5. Schemas first. `schemas/*.schema.json` are the contracts between layers. Change the schema, then the code.
6. Every match is replayable: same seed → identical output. No unseeded randomness or wall-clock dependence in `htg/`.
7. Local first. Code runs without Azure; Azure services sit behind an adapter with a local implementation.

## Data rules
- Only synthetic data at runtime. Real open data (StatsBomb, SkillCorner) is for calibration only and lives in
  git-ignored `data/raw/`. Never commit raw rows; only aggregates in `data/calibration/`.
- Teams and players are fictional. Never use real club, player, league or Premier League names or branding.
- `truth.json` (hidden scenarios) must never be read by detectors, the engine or agents. Only `eval/` may read it.
- Tune thresholds on seeds 1-10 only. Report numbers on seeds 11-30. Never tune on reporting seeds.

## Commands (macOS: use `python3` for the first venv; inside the venv `python` works)
```bash
python3 -m venv .venv && source .venv/bin/activate     # needs Python 3.11+; else: brew install uv && uv venv --python 3.12
pip install -e ".[dev]"
ruff check . && pytest            # must pass before every commit
python -m htg.generate --seeds 1 2 3
python -m htg.validate            # only after a generator change
```

## Layout
- `schemas/` contracts · `htg/` Python package · `tests/` pytest · `prototype/` day-0 sound prototype (reference only)
- Planned: `htg/engine/`, `htg/narration/`, `htg/speech/`, `htg/adapters/`, `services/engine`, `web/` (single-page client: `live.html` markup, `app.css`, `js/*.js` classic scripts in load order),
  `eval/`, `infra/` (Bicep + azd)

## Conventions
- Python 3.11+, type hints, small pure functions; ruff line length 140.
- Tests for every detector, the Verifier and the Director. Use fixed seeds in tests.
- Branch per task (`day2/state-engine`), small commits, PR into `main`, CI green before merge.
- Commit messages: imperative, what and why (`Add pressure-shift detector scored against truth`).
- No secrets in code or git. Local config via `.env` (see `.env.example`); in Azure, managed identity.
- README is for the jury and in English. Keep its numbers in sync with real measurements; never claim
  untested results (e.g. no "validated with blind users" unless it happened).

## Microsoft stack actually used
Microsoft Foundry (model deployment, narrator + verifier calls, tracing, evaluations) · Azure AI Speech (neural / MAI-Voice TTS, TR + EN) ·
Azure Container Apps (one app: engine + static client) · Application Insights · Key Vault / managed identity · azd + Bicep · GitHub Actions.
Deterministic parts (Director, detectors, sonification) are intentionally not agents.
