# 2026-10-26: harden the public demo (server only, small)

Context: a read-only audit (2026-10-25, report kept outside the repo) found that one stranger with a script can crash a replica or
flood Foundry and Speech on the public URL, which stays open until judging ends (Nov 10). The demo for the judges must not degrade.
Server only; the client and the listening view do not change. Do this **before** `2026-10-26-listen-view.md`; the owner deploys both
together. See "Scope and token budget" in CLAUDE.md.

Done when: parts 1-4 committed, `ruff check . && pytest` pass, STATUS updated. Each part small; one commit per part.

## Token budget (strict)
- `services/engine/serve.py`: read only around the lines named below (`grep -n` first). `services/engine/recap.py` lines ~20-40.
- No browser, no screenshots, no client files, no infra changes.
- Narrow tests while working (`pytest tests/test_serve.py -k ...`); full suite once before each commit.
- Do not re-plan. Out-of-list audit findings are decided (see "Not doing").

## 1. Unbounded `prefs` list (high: one socket can OOM the replica)
`serve.py` ~283: `prefs.append(msg)` stores every unrecognised client message for the whole session.
- Keep only the message types `apply_listener_message` actually handles (grep it; expected `set_mode`, `set_favourite`), validated
  the same way it validates them, and keep **only the latest of each** (a dict keyed by type; replay in that order where `prefs`
  is replayed today). Anything else is ignored.
- Test: 1,000 junk messages + two `set_mode` -> one stored entry, the last mode.
Commit: `Keep only the latest valid preference per type instead of every client message`.

## 2. Recap flood (high: Foundry + Speech cost, and it starves narration)
`serve.py` ~276 spawns a new "missed" recap per `recap_request` with no limit; recap work shares the default thread pool with
narration (`resolve.py` ~39) and commentary.
- Per session: at most **one recap in flight** and a **cooldown of 20 s** after it finishes (monotonic clock in the server is fine;
  this is `services/`, not `htg/`). A request during either is ignored. The client already shows "Preparing…" while busy
  (`setRecapBusy`), so a human pressing twice simply gets the first recap.
- Run recap work on its own small executor (`ThreadPoolExecutor(max_workers=2)`, module level), so a recap burst cannot starve
  narration and commentary.
- Test: two `recap_request`s back to back -> one recap task; after the cooldown -> a second is accepted (patch the clock).
Commit: `Allow one recap per session at a time with a 20 s cooldown on its own executor`.

## 3. Sessions per client (medium: one script can hold every slot and lock the judges out)
`serve.py` ~76 / ~233: `MAX_SESSIONS = 20` per replica, no per-client cap.
- Cap open sessions per client IP at **4** (first hop of `X-Forwarded-For`, which Azure Container Apps ingress sets; fall back to
  the socket's remote address locally). Over the cap: close with the same `1013` "busy" path used today. Count released on close
  (also on errors: use the existing cleanup path).
- 4, not 2: judges may share an office NAT, and the owner records the video with several tabs.
- Test: five connections from one IP -> the fifth is refused; another IP is accepted.
Commit: `Cap open sessions per client IP at 4`.

## 4. NaN inputs (low, one commit)
- `serve.py` ~147-152: `?delay=nan` passes the clamp (`max(nan, 0)` is nan). Use `math.isfinite`, else the default.
- `recap.py` ~26-27: `since_min` NaN / inf -> treat as missing (`math.isfinite`).
- `.env.example:8`: replace the real Foundry endpoint with `https://<resource>.services.ai.azure.com/api/projects/<project>`.
- Tests: one each for the two NaN cases.
Commit: `Reject non-finite delay and since_min; use a placeholder endpoint in .env.example`.

## Not doing (decided)
- WebSocket `origins=`: low value, and a wrong list breaks the live demo and local dev. Not now.
- A server idle timeout: the client already stops a hidden tab after 2 min of suspended sound or 45 min hidden (`main.js` ~202-220,
  README "Limitations"); a server timeout would cut listeners with a locked screen, a feature we show. A scripted client is bounded by
  part 3 and the deployment TPM.
- Disk cache size cap: falls away with part 2.
- Foundry portal links in `eval/results/foundry_eval.md`: kept (evidence for the jury; no credential).
- Squad names that match common real surnames: kept (fictional clubs; regenerating the cache is not worth the risk).
- `htg/validate.py` reads `truth.json`: it is the generator's validator, not a detector, engine or agent. Note it in STATUS; no move.

## After
- STATUS: one short section "Hardening (2026-10-26)" with what changed and the decided "not doing" lines; also replace the stale
  "Last updated / Next" line at the top. Move this file to `docs/tasks/done/`.

## Owner (not Claude Code)
- Azure portal: a subscription **budget with an email alert** (5 min).
- Check the Foundry model deployment's **TPM limit** (the real hard cap on a runaway; 429 falls back to templates).
- Confirm `web/icon*` are self-made; check the MAI-Voice preview terms allow a public demo.
- Optional: future commits with the GitHub noreply email.
