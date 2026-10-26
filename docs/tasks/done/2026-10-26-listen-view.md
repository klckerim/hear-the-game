# 2026-10-26: listening view (the app's first screen for blind and low-vision fans)

Context: the product is for people who cannot see the screen, but the first screen today is a sighted "broadcast desk" (pitch,
timeline, feed, settings). The jury must feel who the app is for in the first seconds. This task adds a **listening view** as the
default first screen and keeps the current desk as the second view, reached with "Show the pitch & data". Client only; the server
does not change. Prerequisite: the client split (`web/app.css`, `web/js/*.js`) and the pre-freeze round are done and deployed.
See "Scope and token budget" in CLAUDE.md. English first.

Done when:
- A first visit opens the listening view; a blind user with VoiceOver can pick a match, start, stop, jump to the next moment and ask
  "Catch me up" without seeing the screen.
- The desk view works exactly as before; the two views switch both ways while listening without stopping the sound.
- `ruff check . && pytest` pass; the owner has tried it with VoiceOver on iOS.
- STATUS updated, including the stale "Last updated / Next" line at the top (it still lists the phone status bar, team picker and
  start-screen decision as next). Owner's decision (2026-10-25): **no Azure portal screenshots in the README**; remove any
  "Owner, later: screenshots" lines from STATUS.

## 0. Fix first: narration cuts the commentator off (owner heard it, 2026-10-25)
At a big moment a commentator line was cut off just as it started by another voice; the line still showed in the feed. Cause (read in
`web/js/speech.js`, `say()`): a narration sentence waits for a callout under way and for a **goal** commentator line, but for any other
commentator line it calls `stopComm()` and cuts it. Fix: a narration sentence waits for a commentator line under way whatever it is
(same loop as the goal case, cap 8 s for a goal line and 6 s for others; stop waiting on a new session), then plays. Recaps and the
tour keep their current behaviour. Update the comment above `COMM_WAIT_S` ("narration comes first" is no longer true for a line
already playing). One commit. Two details that make the fix hold:
- **Hold the slot while waiting.** While the sentence waits, the next commentator line must not start in the gap after the current
  one ends (`commentaryLine` only checks `tour.on || clip || comm || speaking`, all empty in that gap). Add a small counter (like
  `callouts.held`, e.g. `sayHeld`) that `say()` raises while it waits and lowers when it plays or gives up; `commentaryLine` treats
  it as "voice busy" (that line then waits up to `COMM_WAIT_S` as today, or is dropped).
- **Caption follows the voice.** `say()` sets the caption and its tag at the top, before any wait, so today the caption shows the
  narration while the commentator is still speaking. Move `setCaption` / `captionTag` / `captionMine` below the waits (keep the
  `!L_voice` path showing the caption at once). The feed rule stays: a line joins the feed when it ends or is cut off.

## 1. One page, two views (decisions, do not re-plan)
- **Same page, same session code.** `body[data-view="listen" | "desk"]` decides what shows. No second HTML page, no copy of the
  session logic. Listen-only elements are few and live in `web/js/listen.js` + a `listen` block in `app.css` (or `web/listen.css`).
- **Which view opens:** `localStorage` `htg.view` (wrap in try/catch); first visit = `listen`. `?view=listen|desk` overrides and is
  stored (for the video and the testing instructions).
- **Switch:** "Show the pitch & data" (TR "Sahayı ve veriyi göster") in the listening view; "Listening view" (TR "Dinleme görünümü")
  in the desk's header. Switching never stops or restarts the session unless the mode changes (see 1.4).
- **Mode:** the listening view always plays in **Audio only** (eyes-free fan mode: callouts and live commentator on). The desk keeps
  the listener's own mode choice. Switching view while listening changes the mode only if it differs, through the existing mode-switch
  path (it already resumes where the listener is). The forced Audio only mode is **not** written to `htg.mode`: that key keeps the
  desk's choice, and returning to the desk restores it (Analyst stays Analyst after a trip through the listening view and a reload).
- **Desk switch button placement:** the phone player bar was just fixed for overflow (`flex-wrap: nowrap`, status ellipsises). Put
  "Listening view" in the desk's header (next to the language control), not in the player bar, so it cannot push the bar again.
  One button, all widths. Check at 390 px.

## 2. What the listening view shows (DOM order = reading order = visual order)
1. `h1` "Hear the Game" + one line "Football you can hear. Put on headphones." (TR from the `T` dictionary).
2. Current match ("Northport v Valemont"), score and clock in large text (the existing score bar elements, restyled; no new ids).
3. **Start listening / Stop** (existing button): full width, at least 64 px tall.
4. Live / Highlights (existing toggle, as two large buttons with `aria-pressed`).
5. Next moment, Catch me up (existing buttons, large).
6. Status line (existing `#status`, `role="status"`).
7. Caption (existing, large text for low-vision users; its `aria-live` rule in `syncLiveRegions` stays as it is).
8. **Choose a match** (`h2`) + the match list (see 3).
9. Language (existing interface-language control; the commentary language follows it unless the listener changed it in Settings).
10. Sound tour offer on the first visit (existing banner and tour).
11. Keyboard shortcuts in one line (only the shortcuts that exist: Space, N; add none).
12. "Show the pitch & data".

Hidden in this view: pitch, timeline, Why card, commentary feed, Analyst panels, mode switch, Settings box, the desk's match picker button.
The favourite club and player chosen in the desk still apply (no new settings here).

## 3. Match choice, the easiest way without sight (decision)
- Reuse the desk's new match cards (`2fd7e8e`: buttons, your club first with "your team", current one `aria-current`), but in the
  listening view the list is **always open** under the `h2` (no picker button, no popover): VoiceOver swipes straight through it.
  Each card reads as "Northport versus Valemont" (+ "your team"); club-colour dots are `aria-hidden`.
- **Never show or speak the final score** in the list (spoiler).
- In this view, activating a card **starts listening to that match at once** (Live from the default start the desk uses, or
  Highlights if selected) and moves focus to Start/Stop, so the next double tap stops it. Swiping through the list activates nothing,
  so the desk's rule "a match change waits for Start" is not needed here; the desk keeps that rule.
- **iOS audio unlock:** the card's click handler must reach the same start path as Start (`initAudio(); ctx.resume()` in
  `session.js`, plus `primeVoice()` if Start calls it) synchronously, with no `await` or `setTimeout` before it; otherwise iOS
  Safari keeps the AudioContext suspended and the first tap plays nothing.
- If a session is already playing another match, the card switches to the new match (same path as the desk's match change +
  Start). Activating the card of the match already playing does nothing except move focus to Start/Stop.
- The status line then reads as today.

## 4. Screen reader rules (acceptance)
- No new live regions. While listening without touching the screen, VoiceOver speaks only: the status line on start, match change
  and Highlights cut. Everything else is heard as audio (callouts, commentary, narration).
- Every control is a real button or select with a visible label; focus ring visible on the dark theme; target size >= 48 px.
- Heading structure: `h1` app, `h2` "Choose a match" (and `h2` for any other group you add); nothing decorative is announced
  (`aria-hidden` on icons).
- Text contrast >= 4.5:1, body text >= 18 px in this view, works at 320 px width without horizontal scroll, respects
  `prefers-reduced-motion`.

## 5. Check
- Headless Chrome against local `serve` (text checks, at most 4 screenshots in total: listen 1440 + 390, desk 1440 after a switch, TR
  listen 390): first visit opens listen; `?view=desk` opens desk and is remembered; a match button starts a session (`hello` arrives,
  status updated); view switch while listening keeps the socket open; Analyst in desk -> listen switches to Audio only and back to
  Analyst on return; no console errors.
- List for the owner what to try with VoiceOver on iOS (one short list in STATUS).

## Commits (one after each part; no deploy, the owner deploys)
1. Step 0 (commentator cut-off). 2. Views + switch + mode handling (section 1, CSS skeleton). 3. Listening view content and the
always-open match list (sections 2-3). 4. Accessibility pass + checks + STATUS (sections 4-5).

## If time runs short (time box: done by 2026-10-26 18:00 Istanbul)
Cut in this order, never half-build: the keyboard-shortcut line (2.11), the tour offer in the listening view (2.10; the desk keeps
it), large-button styling of Live / Highlights (keep the existing toggle). Never cut: step 0, first-visit listen, the switch both
ways, the always-open match list.

## Token budget

- At most 4 screenshots in total (section 5); no other image reads. Prefer text checks (DOM queries, console output).
- Narrow tests while working; full `ruff check . && pytest` once before each commit.
- Do not re-plan: the decisions above are final. If something blocks, stop and write the question in STATUS.

## Owner (not Claude Code)
- VoiceOver on iOS: open the app, swipe through the listening view, pick a match, stop, Next moment, Catch me up, switch to desk.
- `azd deploy` once after this task; then the README task and the video use the listening view as the opening shot.

## Out of scope
New features, voice commands, a second settings menu, onboarding beyond the existing tour, server changes, README (next task).

## Addendum (owner, after trying a first version; applies to sections 2 and 4)
Design: mobile first, like a radio / podcast "now playing" screen, calm. One column, max ~560 px; a "now playing" card on top (match,
clock and score large and bold, the caption inside under them); Start / Stop full width under the card (>= 64 px, the strongest
element); Next moment and Catch me up side by side (stack below 360 px); Live / Highlights a full-width two-part segmented control;
then "Choose a match" (h2) with the always-open cards, language and "Show the pitch & data" at the bottom. No small tags, badges or
secondary text except "your team" on a card; colour only for club dots and the focus ring.
Hint line (replaces 2.11), chosen by CSS: touch devices (`(hover: none) and (pointer: coarse)`) "Lock your phone, the match keeps
playing. Headphones tell you the side of the pitch."; desktop the keys line. Both in the DOM, the hidden one `display: none`.
Do not add custom touch gestures or Media Session / lock-screen controls. Commits one per part; at the end push to origin (no deploy).
