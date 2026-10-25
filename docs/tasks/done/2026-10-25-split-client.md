# 2026-10-25: split web/live.html into files (no behaviour change)

Context: `web/live.html` is ~1,700 lines (markup, ~290 lines of CSS, ~1,200 lines of JS in one file). Every client task now reads or
greps one big file. The next task (a listener start screen) touches the client again. This task moves code into files **without
changing a single behaviour**. It is a mechanical cut along the section markers that already exist; no refactor, no renaming.

## Token budget (strict)
- **No screenshots, no image reads, no visual checks.** The owner checks in the browser.
- Do not read `live.html` whole. Get the outline with `grep -n` (the `/* ---------------- x ---------------- */` markers, `<style>`,
  `<script>`), then cut by line ranges with a short script. Do not retype code; move it byte for byte.
- One commit for the split, one for the server route + test. `ruff check . && pytest` once before each commit.

## Target layout
```
web/live.html        markup only (head, body, <link rel="stylesheet" href="app.css">, the <script defer> tags in order)
web/app.css          everything that is in <style> now, unchanged
web/js/i18n.js       constants at the top of the script + the T dictionary + favourite-club storage (up to "audio")
web/js/audio.js      "audio"
web/js/session.js    "live stream" (session start, resetLive, highlights cut, analyst log, recap / "What did I miss")
web/js/stats.js      "analyst stats"
web/js/timeline.js   "evidence timeline" (incl. the Why card)
web/js/speech.js     "narration", "callouts", "live commentator" and the feed
web/js/tour.js       "sound tour"
web/js/pitch.js      "drawing"
web/js/main.js       "wiring"
```
Use the existing markers as the cut points; if a marker falls in a slightly different place than this list, follow the markers and
adjust the file names, do not move functions between sections.

Rules:
- **Classic scripts, not ES modules**, all `defer`, in the original order. They share globals exactly as the single `<script>` does
  today, so nothing needs `import`/`export`. Check that no file runs top-level code that reads something defined in a later file
  (the original order guarantees this; keep it).
- Inline `on...=` handlers in the markup, if any, keep working because the functions stay global.
- Add a one-line header comment at the top of each JS file: what it holds. Nothing else changes.
- `live.html` opened as a file (run_local) must still work: relative paths only (`app.css`, `js/main.js`).

## Server
`services/engine/serve.py` serves only known paths today (`CLIENT`, `ICONS`, `/tour/`, `/callouts/`, ...). Add the new files the
same way: a small allow-list (`/app.css`, `/js/<name>.js` for names that exist in `web/js/`), right content types
(`text/css`, `text/javascript`), no path traversal (reject anything with `..` or a name not in the list). Check the `Dockerfile`
copies `web/` whole (it does: `COPY web web`).

Test (`tests/test_serve*.py`, pick the existing file): parse `web/live.html` for `href`/`src` of local files and assert `serve`
answers 200 with the right content type for each, and 404 for `/js/../serve.py`.

## Check (text only)
- Headless Chrome against a local `serve` (no screenshots): load the page, press Start via CDP, wait ~20 s, print the console
  errors (count + first 5 lines) and whether a `hello` arrived. Expected: 0 errors.
- `wc -l` of every new file into the commit message.

## STATUS
One line under the newest section: client split into `web/app.css` + `web/js/*.js` (classic scripts, same order), no behaviour change,
served by an allow-list in `serve.py`. Update the CLAUDE.md layout line for `web/`.

## Owner (not Claude Code)
Open locally, try Start, a match switch, Highlights, Analyst, the tour, Catch me up; then `azd deploy` together with the next task.

## Out of scope
Any behaviour or style change, renaming, ES modules, a bundler, splitting further than the list above.
