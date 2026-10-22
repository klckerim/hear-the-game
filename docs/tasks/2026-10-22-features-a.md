# 2026-10-22 (evening): rules compliance, clubs, fan/analyst narration, chapters

Context: we compared the repo with the official rules (owner has `OFFICIAL_RULES.md`). Gaps that matter: the rules ask for
"favorite club(s)", for the analyst and the casual fan to get "two genuinely different experiences", and judges will not wait
9.5 minutes for the first goal. Selection rule for all new work: if a judge would not notice it in a 2-minute video or in the first
minute of the demo, do not build it. Category stays **Best Use of Microsoft Foundry**.

Three changes today alter the demo narration cache (club names, persona, chapters). Do them all, then run **one** pregen at the end.
Keep it simple; see "Scope and token budget" in CLAUDE.md. Recap agent, sound tour, timeline and analyst panel are tomorrow, not today.

Done when:
- `docs/design.md` is gone; README, STATUS and other docs no longer point to it.
- Teams are two fictional clubs; the listener can pick a favourite club; the goal sound and the caption reflect it.
- Casual / Audio-only narration uses the **fan** persona, Analyst uses the **analyst** persona; both are cached and verified.
- The listener picks a chapter (Kick-off / First goal / Late drama) before starting; each starts with warmed-up detectors.
- Space starts and stops listening.
- Seed-7 cache regenerated for the chapter windows and both personas; stale clips deleted; size reported.
- `ruff check . && pytest` pass; deployed with `azd deploy`; owner listened.

## 1. Compliance fixes (30 min, first commit)
1. Delete `docs/design.md` (Turkish; rule 4.9 wants all submission material in English). Remove references in README
   ("original design (Turkish)"), STATUS and anywhere else (`grep -rn design.md`).
2. `docs/data.md`: StatsBomb's open-data terms ask users to name StatsBomb as the source **and use their logo** (Media Pack).
   Add an "Attribution" block with the text credit and a placeholder `docs/img/statsbomb-logo.png` (the owner downloads the logo).
   Do not put the logo in the README header or the video. Keep the SkillCorner credit.
3. README: new short section **"Overlay feed (machine-readable)"**: the WebSocket messages are timed JSON (`hello`, `state`,
   `event_cue`, `insight`, `speech`), each with match time `t`; Insights carry `claim_facts` and `evidence` seqs; schemas in `schemas/`.
   One example `insight` and one `speech` message (real, from seed 7, trimmed). Say a broadcast graphics engine could render
   overlays from it; do not claim an integration that does not exist.

## 2. Fictional clubs and favourite club
1. `htg/generate.py` `SQUADS`: replace "the Reds" / "the Blues" (they echo real club nicknames) with two fictional clubs.
   Default names (owner may change before you start; keep them in one constant): HOME **Northport** (red), AWAY **Valemont** (blue);
   same spelling in EN and TR. Check that no real professional club uses the name.
2. **The match must not change.** Names must not feed the RNG. Regenerate committed seeds 1-3 and 7: `events.jsonl`, `ball.parquet`,
   `physical.jsonl`, `truth.json` must be byte-identical (only `meta.json` changes). Add a test that pins a hash of seed 1 events.
   If anything else changes, stop and tell me (detector numbers in README would no longer hold).
3. Update fixtures/docs that print the old names where they describe the current demo (README examples, `docs/listening-test.md`
   instructions and answer key). Leave historical result files (`eval/results/*samples*.jsonl`, dated tables) as they are.
4. Client: "Favourite club" selector (None / Northport / Valemont), remembered in `localStorage` (try/catch). Effects, client-side only:
   - goal by your club: the existing goal figure plus a brighter, longer crowd swell; goal against: short and muted (no fanfare);
   - your club's name in the score bar marked "your team" (text, not only colour);
   - caption tag "your team" when a spoken Insight is about your club.
   Sent to the server with `set_mode`-style message `set_favourite`; the Director gives your club's Insights +1 priority
   (pure function argument, unit test). Narration text stays neutral today (tomorrow's recap uses the perspective), so the cache
   does not multiply by favourite.

## 3. Fan / analyst narration persona
1. `persona` = `analyst` when mode is Analyst, else `fan`. Pass it to the narrator; add it to the narration cache fingerprint.
   `PROMPT_VERSION = 5`. Do not change the Verifier rules.
2. Prompt: one system prompt, a persona block each, one hand-written EN/TR example per Insight type and persona:
   - **fan**: radio excitement, at most one number (prefer none: "the Blues are pressing much higher now"), max 16 words;
     goals and chances are emotional but factual.
   - **analyst**: the key numbers and the comparison (now vs earlier), precise, max 25 words.
   "Prefer none" must still not invent vague claims: every statement must follow from `claim_facts`.
3. Templates stay one set (they are the fallback for both personas).
4. Tests: fingerprint differs by persona; fan example sentences pass the Verifier; cache hit per persona.
5. `eval/narration.py --persona fan|analyst`; run 50 Insights for `fan` (seeds 11-30) and add a row to `eval/results/narration.md`
   (first pass, fallback, latency, mean numbers per sentence for fan vs analyst). Do not rerun the Foundry evaluation.

## 4. Chapters (demo start points)
1. Constant `CHAPTERS` (seed 7): `kickoff` 0', `first_goal` 19' (goal at 22:36), `late` 76' (goals at 79' and 87').
   Verify the minutes against `events.jsonl` before hard-coding. Session length stays 15 match-minutes.
2. Client: chapter buttons before "Start listening" (default `first_goal`), labelled TR/EN in the `T` dictionary, e.g.
   "Kick-off · 0'", "First goal · 19'", "Late drama · 76'". Sent as `/ws?chapter=first_goal`; the server accepts only known
   chapters (unknown -> default). The scorebar shows the correct score at chapter start (from the warm-up), not 0-0.
3. Server: warm all chapters once at start (`warmed()` keyed by start minute, already off the loop); test that a `late` session's
   first `hello`/state has the score of minute 76.
4. Remove the fixed `--start-minute 13` default from the Dockerfile/serve if chapters replace it; `run_local` keeps `--start-minute`.

## 5. Small
- Space toggles start/stop (not while focus is in a select or text field). Mention it next to the button ("Space").
- The "Live · synth_0007" status text becomes "Demo match · seed 7" (TR/EN).

## 6. Pregen once, then deploy
1. `pregen` for seed 7: for each chapter window (start .. start+15 min) and each mode (casual, analyst; audio-only shares casual's
   Insights and the fan persona), narrate + synthesize what the Director speaks. Delete MP3s no longer referenced.
2. Print all new sentences (chapter, minute, persona, EN, TR) to a file `eval/results/demo_sentences.md` for the owner to read before
   listening. Report cache size; if it is above 25 MB, tell me before committing.
3. Update `eval/results/narration.md`, README (clubs, favourite club, personas, chapters, overlay feed), STATUS (what changed, open items).
4. `ruff check . && pytest`, commit, `azd deploy`, then owner checks the deployed demo.

## Owner
- Before you start: confirm or change the club names.
- After pregen: read `demo_sentences.md`, then listen to 5 clips per persona and language. Check the new names' pronunciation in Turkish.
- Download the StatsBomb logo from their Media Pack into `docs/img/statsbomb-logo.png`.

## Out of scope today
Recap agent, sound tour, insight timeline, analyst stats panel, MCP, accessibility settings, generator changes, other seeds.
