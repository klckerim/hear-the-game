# Hear the Game

Microsoft × Premier League "Inside the Game" hackathon entry. Synthetic football events become spatial sound
(synthesized on the listener's device) and short, verified, multi-language narration (Microsoft Foundry agents +
Azure AI Speech). Target users: blind and partially sighted fans, and anyone who can't look at a screen.

Deadline: submission 2026-10-27 23:59 PT (2026-10-28 09:59 Istanbul). Plan to submit on 2026-10-27.
Full design: `docs/design.md`. Current task: the newest file in `docs/tasks/`.

## Non-negotiable rules
1. Numbers come from code, words from the LLM. xT, pressure, durations, scores are computed deterministically.
   The LLM only turns given facts (`claim_facts`) into sentences.
2. No sentence ships without evidence. Every Insight carries the event `seq` numbers it rests on. The Verifier
   rejects any sentence whose numbers or names are not in `claim_facts`.
3. Sound never waits for the LLM. The fast path (state → sound) and the slow path (insight → narration) are
   independent; if narration fails, sound continues.
4. The server sends data, the device makes the sound. Speech clips are the only audio sent over the wire.
5. Schemas first. `schemas/*.schema.json` are the contracts between layers. Change the schema, then the code.
6. Every match is replayable: same seed → identical output. Never introduce unseeded randomness or wall-clock
   dependence in `htg/`.
7. Local first. Every Azure service sits behind an adapter with a local implementation
   (`EventSource`, `Broadcaster`, `Store`, `BlobStore`, `Speech`). Code must run without Azure.

## Data rules
- Only synthetic data at runtime. Real open data (StatsBomb, SkillCorner) is for calibration only and lives in
  git-ignored `data/raw/`. Never commit raw rows; only aggregates in `data/calibration/`.
- Teams and players are fictional. Never use real club, player, league or Premier League names or branding.
- `truth.json` (hidden scenarios) must never be read by detectors, the engine or agents. Only `eval/` may read it.

## Commands
```bash
pip install -e ".[dev]"
ruff check . && pytest            # must pass before every commit
python -m htg.generate --seeds 1 2 3
python -m htg.validate            # after any generator change; keep KS and per-match ratios in README current
```

## Layout
- `schemas/` contracts · `htg/` Python package · `tests/` pytest · `prototype/` day-0 sound prototype (reference only)
- Planned: `htg/engine/`, `htg/narration/`, `htg/speech/`, `htg/adapters/`, `services/engine`, `services/api`,
  `web/` (TypeScript + Vite, Web Audio), `eval/`, `infra/` (Bicep + azd)

## Conventions
- Python 3.11+, type hints, small pure functions; ruff line length 140.
- Tests for every detector, the Verifier and the Director. Use fixed seeds in tests.
- Branch per task (`day2/state-engine`), small commits, PR into `main`, CI green before merge.
- Commit messages: imperative, what and why (`Add pressure-shift detector scored against truth`).
- No secrets in code or git. Local config via `.env` (see `.env.example`); in Azure, managed identity.
- README is for the jury and in English. Keep its numbers in sync with real measurements; never claim
  untested results (e.g. no "validated with blind users" unless it happened).

## Microsoft stack (keep usage real, not decorative)
Microsoft Foundry (models, tracing, evaluations) · Microsoft Agent Framework (narration workflow) ·
Azure AI Speech (neural / MAI-Voice TTS) · Event Hubs · Container Apps · Web PubSub · Cosmos DB · Blob ·
Application Insights · Static Web Apps · azd + Bicep · GitHub Actions. Deterministic parts (Director, detectors,
sonification) are intentionally not agents.