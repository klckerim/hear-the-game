# 2026-10-24: pre-freeze round, light part (no new features)

Context: Features D, the live commentator and the "broadcast desk" layout are deployed (owner, 2026-10-23). This round fixes small
things seen on the deployed app and drafts the submission text. README final pass, screenshots and the deployed latency measurement
move to the next task, because the owner is considering a new start screen (listener view) that changes both.
See "Scope and token budget" in CLAUDE.md. English first.

## Token budget for this task (strict)
The owner's weekly limit is nearly used up. This task must stay cheap:
- **No screenshots, no image generation, no reading images or PDFs.** No headless-Chrome visual checks. The owner checks the
  result in a browser.

- Do not read README whole for part 4; grep the sections you need.
- Narrow tests while working; `ruff check . && pytest` once before each commit. Short command output (`| tail`).
- If something needs a visual check, stop and list it for the owner instead of checking it yourself.

Done when:
- Parts 0-2 are committed (one commit per part); the owner deploys once and checks in the browser.
- `docs/submission.md` holds the draft texts.
- `ruff check . && pytest` pass; STATUS is up to date.

## 0. Housekeeping (5 min)
- STATUS: Features D and the layout redesign are deployed and checked by the owner (2026-10-23); update the "Last updated / Next" line
  at the top (it still says "waiting for deploy"). `docs/tasks/2026-10-24-features-d.md` is already in `done/`.

## 1. Listening state in the caption
After Start, the caption still says "Press Start listening..." until the first sentence. Replace it on Start with a short listening
state ("Listening · the commentator speaks in a few seconds" in fan modes; "Listening · tactical notes appear when something changes"
in Analyst), TR and EN, from the `T` dictionary. Back to the idle text on Stop.

## 2. Commentary feed bugs
1. **Feed grows on desktop.** On phones the feed keeps its fixed box and scrolls; on desktop (>= 861 px) the box grows with every
   line and pushes the page down. Likely cause: in the desk grid the listening column's intrinsic height (the feed's content) sets the
   row height, so `.d-listen .feed { height: auto; }` never gets a bound. Fix in CSS only: the feed fills the space beside the pitch
   column and scrolls inside (e.g. `contain: size` on the feed, or `min-height: 0` + `overflow: hidden`, so the pitch column alone sets
   the row height; keep the `minmax(220px, 1fr)` floor). Reason it through in the CSS; the owner verifies at 1440x900 and 1280x800.
2. **Feed mixes sessions.** Today the feed is kept for the whole match (`resetLive`, see the comment above it), so Highlights -> Live
   (or back) leaves the old lines and new ones land on top out of match order (a 36' line above a 76' line), and Stop -> Start adds
   lines for minutes that already have one. New rule, in one place (`resetLive`):
   - Keep the feed only when the new session is the **same match, same way to watch (Live / Highlights)** and starts **at or after
     the newest line's match time** (Next moment, a forward timeline click, a mode switch that resumes where the listener is).
   - Otherwise clear it: match switch, Live <-> Highlights, a jump backwards, Start after Stop that replays an already-heard stretch.
   - De-duplicate in `addFeed`: a line with the same segment id (or the same match second and text, if the message has no id) is not
     added twice.
   Update the comment above `resetLive` and the STATUS line that says the feed "stays across jumps". If the keep/clear decision can be
   a small pure function, give it a few lines of logic that are easy to read; no test framework for the client.
   For the owner to check: Highlights 76' -> Live 36'; Live -> Highlights; Stop -> Start; one forward Next moment (feed kept).

## 3. Submission drafts (text only)
`docs/submission.md` (English): project name; one-line tagline; elevator pitch (~100 words: what it is, who it is for, which
Microsoft technologies, what problem it solves); a longer description (~300 words) that follows the README; category (Best Use of
Microsoft Foundry) with 3-4 sentences on why; testing instructions for judges (link `<LIVE_URL>`, headphones, Start, Highlights, modes,
language, session limits: one listener session per tab, max 20 at once, a hidden tab closes 2 minutes after the browser suspends its
audio); tech list. Facts only from the README and `eval/results/` files. Mark with `<!-- UI -->` every sentence that describes the
screen layout: it may change with the next task.

## Moved to the next task (after the owner's decision on the start screen)
README final pass and "Try it" box, Claude-made screenshots (headless Chrome), bug bash across matches/modes/languages, deployed latency
re-measure (`eval.latency`).

## Owner (not Claude Code)
- `azd deploy` once after parts 1-2, then check on the phone and desktop (the checks listed in part 2).
- Azure portal screenshots: `docs/img/trace.png`, `foundry-eval.png`, `metrics.png`.
- iOS Safari: lock the screen while listening; does the sound continue? Result into STATUS.
- Azure credit end date must be after Nov 10; `minReplicas` stays 1 until then.

## Out of scope
New features, new matches or clubs, prompt changes, generator changes.
