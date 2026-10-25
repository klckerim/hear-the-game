# 2026-10-24: pre-freeze round (no new features)

Context: Features D, the live commentator and the "broadcast desk" layout are deployed (owner, 2026-10-23). The plan is about
1.5 days ahead. This round adds nothing new: it fixes small things seen on the deployed app, makes every claim in the README match
the product and a measured number, and prepares the material the video and the submission need.
After the freeze only fixes that keep the demo running. See "Scope and token budget" in CLAUDE.md. English first.

Done when:
- The small fixes below are in, deployed once by the owner, and checked.
- README reads as the final submission text (numbers sourced, screenshots in, "not built" list correct, live demo link slot).
- Deployed latency is re-measured for Live and Highlights.
- `docs/submission.md` holds the draft pitch, description and testing instructions (owner edits and pastes them).
- `ruff check . && pytest` pass; STATUS is up to date; finished task files are in `docs/tasks/done/`.

## 0. Housekeeping (5 min)
- Move `docs/tasks/2026-10-24-features-d.md` to `docs/tasks/done/`; STATUS: Features D and the layout redesign are deployed and
  checked by the owner (2026-10-23); update the "Last updated / Next" line at the top (it still says "waiting for deploy").

## 1. Small fixes seen on the app (~1 h)
1. After Start, the caption still says "Press Start listening..." until the first sentence. Replace it on Start with a short
   listening state ("Listening · the commentator speaks in a few seconds" in fan modes; "Listening · tactical notes appear when
   something changes" in Analyst), TR and EN.

2. Bug bash in headless Chrome, all six matches, Live and Highlights, Casual and Analyst, EN and TR, 1440 and 390 px: list every
   console error, overlap, clipped text or wrong score in STATUS and fix what takes under 15 minutes; leave the rest listed.

3. The live commentary feature has issues on the web version: as new commentary entries are added, the list simply extends downwards. On mobile, however, it works correctly—the text box does not expand as entries are added; instead, it remains a fixed size and can be scrolled through.

4. When switching from the "highlights" section to the "live" section, previous commentary entries are not cleared; instead, new entries are simply appended on top of the existing ones. For example, if there is a commentary entry for the 76th minute in the highlights section, and you switch to the live section to add new commentary, an entry for the 36th minute might appear right above it. The same issue occurs when switching in the opposite direction—the previous entries remain. Furthermore, stopping and restarting the commentary does not clear the existing entries, and new commentary continues to be added, even for minutes that already have entries.

## 2. README as the final text (~2 h)
1. Read it top to bottom as a judge: every feature described exists, every number links to a file in `eval/results/` (or
   `data/synthetic/validation.md`) and matches it; the commentary numbers are the prompt v4 run.
2. Sections to check: what you hear / see (match choice, Live / Highlights, callouts, live commentator, feed, recap, timeline, Why,
   Analyst), architecture diagram (commentator and Recap agent nodes, MAI-Voice), Microsoft stack table (Foundry model, Foundry
   tracing, Foundry evaluations, Recap agent, Azure AI Speech incl. MAI-Voice (preview), Container Apps, ACR, App Insights, Log
   Analytics, managed identity, azd + Bicep, GitHub Actions), built vs not built, limitations (honest: Verifier checks names and
   numbers, not every adjective; synthetic data; iOS background audio untested unless the owner tested it; no blind-user validation
   unless the listening test happened).
3. Screenshots you can make yourself with headless Chrome against a local server, saved to `docs/img/` and embedded: desktop
   Casual while the commentator speaks (caption + feed), timeline with the Why card open on an Insight, Analyst view with stats,
   phone view. Replace the placeholder comment. Azure portal screenshots (trace, evaluation run, metrics) are the owner's; leave a
   marked slot for each.
4. A "Try it" box near the top: live demo link (placeholder `<LIVE_URL>`, the owner fills it in at submission), "use headphones",
   "pick a match, press Start, or try Highlights", and what to expect in the first 30 seconds.
5. Keep it under ~400 lines; move detail to `docs/` if needed.

## 3. Deployed latency (~30 min)
`eval.latency` against the deployed app (owner gives the URL locally; do not commit it): Live (Casual, 20 s delay) and Highlights,
1 and 5 sessions: Start to first sound, state jitter, commentary line latency and late drops as seen by the client. Update
`eval/results/latency.md` and the README table.

## 4. Submission drafts (~30 min)
`docs/submission.md` (English): project name; one-line tagline; elevator pitch (~100 words: what it is, who it is for, which
Microsoft technologies, what problem it solves); a longer description (~300 words) that follows the README; category (Best Use of
Microsoft Foundry) with 3-4 sentences on why; testing instructions for judges (link, headphones, Start, Highlights, modes,
language, session limits: one listener session per tab, max 20 at once, a hidden silent tab closes after 2 minutes); tech list.
Facts only from the README and results files.

## Owner (not Claude Code)
- `azd deploy` once after parts 1-2, then check on the phone and desktop.
- Azure portal screenshots: one App Insights trace (narration span with Verifier attributes and the model call), the Foundry
  evaluation run, the metrics chart; save as `docs/img/trace.png`, `foundry-eval.png`, `metrics.png`.
- iOS Safari: lock the screen while listening; does the sound continue? Result into STATUS and README limitations.
- Azure credit end date must be after Nov 10; `minReplicas` stays 1 until then.
- Listening test if a participant is available (protocol in `docs/listening-test.md`).

## Out of scope
New features, new matches or clubs, prompt changes (unless a README claim is wrong), generator changes.
