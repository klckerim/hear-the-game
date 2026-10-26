// Wiring: controls, events and the start-up calls.
/* ---------------- wiring ---------------- */
$("playBtn").addEventListener("click", () => { endTour(); live.ws ? stopListening() : connect(); });
$("tourBtn").addEventListener("click", () => tour.on ? endTour() : runTour());
$("tourClose").addEventListener("click", () => { if (tour.on) endTour(); store.set(TOUR_DONE, "1"); renderTourBtn(); });
loadTour().then(steps => { tour.steps = steps && steps.length ? steps : null; renderTourBtn(); });
// The label says what a press does ("Hide pitch" / "Show pitch"), so there is no aria-pressed: a screen reader would read
// "Show pitch, pressed".
function setBlind(on) {
  const b = $("blindBtn");
  b.classList.toggle("on", on); b.dataset.i18n = on ? "showBtn" : "blindBtn"; b.textContent = t(b.dataset.i18n);
  $("blind").hidden = !on;
}
$("blindBtn").addEventListener("click", () => setBlind($("blind").hidden));
["L_ball", "L_press", "L_crowd", "L_cue"].forEach(id => $(id).addEventListener("change", applyLayers));
// Callouts default on in the fan modes and off in Analyst (it reads the log); the listener's own choice is kept per group, so a
// trip to Analyst and back does not undo it.
const calloutKey = () => "htg.callouts." + (mode === "analyst" ? "analyst" : "fan");
const calloutsWanted = () => { const v = store.get(calloutKey()); return v === null ? mode !== "analyst" : v === "1"; };
$("L_callout").addEventListener("change", () => {
  store.set(calloutKey(), $("L_callout").checked ? "1" : "0");
  if (!$("L_callout").checked) stopCallout();
});
$("L_voice").addEventListener("change", () => { if (!$("L_voice").checked) stopSpeech(); syncLiveRegions(); });
// While the app speaks (Narration layer on, or the tour), the caption and recap must not also be announced by the screen reader:
// both voices talked at once. With the Narration layer off, the screen reader reads them instead.
function syncLiveRegions() {
  const v = $("L_voice").checked || tour.on ? "off" : "polite";
  $("caption").setAttribute("aria-live", v); $("recap").setAttribute("aria-live", v);
}
function setTeamNames() {
  for (const [side, id] of [["HOME", "Home"], ["AWAY", "Away"]]) {
    const i = teamInfo(side);
    if (!i) continue;
    $("name" + id).textContent = i["name_" + lang()]; $("dot" + id).style.background = teamColor(side);
  }
}
// The six clubs of the league (or, opened as a file, the two of the session); the favourite applies to whichever match has it.
function fillClub() {
  const sel = $("club"), clubs = league ? Object.entries(league.clubs).map(([id, c]) => [id, c.name])
    : ["HOME", "AWAY"].map(s => teamInfo(s)).filter(i => i && i.club).map(i => [i.club, i["name_" + lang()]]);
  sel.replaceChildren(new Option(t("clubNone"), ""), ...clubs.map(([id, name]) => new Option(name, id)));
  sel.value = clubs.some(([id]) => id === favClub) ? favClub : "";
  club = ["HOME", "AWAY"].find(s => favClub && teamInfo(s) && teamInfo(s).club === favClub) || "";
  $("yoursHome").hidden = club !== "HOME"; $("yoursAway").hidden = club !== "AWAY";
  renderSettingsSum();
}
// Match picker: a button with the current match; it opens a list of match cards, the favourite club's matches first, marked "your
// team". Cards are plain buttons (Tab between them), not radios: an arrow key must not switch the match. Escape or a click outside closes.
function matchFace(m) {  // "● NORTHPORT – VALEMONT ●": each name in one line, the pair wraps between the clubs only
  const side = s => { const e = document.createElement("span"), d = document.createElement("i"); e.className = "mt"; d.className = "dot";
    d.setAttribute("aria-hidden", "true"); d.style.background = COLOR[m.teams[s].color] || "#ccc"; e.append(...(s === "HOME" ? [d, m.teams[s]["name_" + uiLang]] : [m.teams[s]["name_" + uiLang], d])); return e; };
  const dash = document.createElement("span"); dash.className = "vs"; dash.textContent = "–"; dash.setAttribute("aria-hidden", "true");
  return [side("HOME"), dash, side("AWAY")];
}
function fillMatches() {
  $("matchbar").hidden = !league;
  if (!league) return;
  const mine = m => !!favClub && (m.home === favClub || m.away === favClub), cur = curMatch();
  const caret = document.createElement("span"); caret.className = "caret"; caret.setAttribute("aria-hidden", "true"); caret.textContent = "▾";
  $("matchBtn").replaceChildren(...matchFace(cur), caret);
  $("matchBtn").setAttribute("aria-label", `${t("matchLabel")}: ${cur.teams.HOME["name_" + uiLang]} – ${cur.teams.AWAY["name_" + uiLang]}`);
  $("matchList").replaceChildren(...[...league.matches.filter(mine), ...league.matches.filter(m => !mine(m))].map(m => {
    const li = document.createElement("li"), b = document.createElement("button");
    b.type = "button"; b.dataset.id = m.id; b.append(...matchFace(m));
    if (m.id === cur.id) b.setAttribute("aria-current", "true");
    if (mine(m)) { const y = document.createElement("span"); y.className = "yours"; y.textContent = t("yourTeam"); b.append(y); }
    const name = t("versus").replace("{home}", m.teams.HOME["name_" + uiLang]).replace("{away}", m.teams.AWAY["name_" + uiLang]);
    b.setAttribute("aria-label", mine(m) ? `${name}, ${t("yourTeam")}` : name);  // never the score: the list must not spoil a result
    li.append(b); return li;
  }));
}
function openMatches(on) {
  $("matchList").hidden = !on; $("matchBtn").setAttribute("aria-expanded", String(on));
  if (on) ($("matchList").querySelector("[aria-current]") || $("matchList").querySelector("button")).focus();
}
function setMatch(id) {
  if (live.ws) stopListening();
  matchId = id; store.set("htg.match", matchId); startT = 0;
  resetLive(); applyMatch();  // nothing of the old match stays: caption, feed, log, markers, Why
}
function pickMatch(id) {
  openMatches(false); $("matchBtn").focus();
  if (id === curMatch().id) return;
  setMatch(id); readyFor(); idleCaption();
}
function applyWatch() { document.querySelectorAll("#watch button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.watch === watch))); renderTimeline(); }
// Before Start (or after a new match is picked): names, colours, clubs and the timeline come from the fixture list.
function applyMatch() {
  if (!live.ws) { live.teams = null; live.moments = null; live.dur = Infinity; live.windows = null; $("score").textContent = "0 – 0"; }
  setTeamNames(); fillClub(); fillMatches(); renderTimeline(); renderStats();
  if (!live.ws) { $("status").textContent = readyLine(); fillFav(curMatch() ? curMatch().teams : null); }
}
function sendClub() { if (live.ws && live.ws.readyState === 1) live.ws.send(JSON.stringify({ type: "set_favourite", team: club || null })); }
// The two squads of the current match: from the session's hello, or before Start from the fixture list.
function fillFav(teams) {
  const sel = $("fav"), keep = sel.value; sel.replaceChildren(new Option(t("favNone"), ""));
  if (!teams || !teams.HOME.players) return;
  for (const side of ["HOME", "AWAY"]) {
    const g = document.createElement("optgroup"); g.label = teams[side]["name_" + lang()];
    teams[side].players.forEach(p => g.append(new Option(p.name, p.id))); sel.append(g);
  }
  sel.value = keep;
}
function flashFav() { const c = $("captionTag"); c.classList.remove("fav-flash"); void c.offsetWidth; c.classList.add("fav-flash"); }
function sendMode() { if (live.ws && live.ws.readyState === 1) live.ws.send(JSON.stringify({ type: "set_mode", mode })); }
function applyMode() {
  document.body.dataset.mode = mode;
  document.querySelectorAll("#modes button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  const eyes = mode === "eyes_free";  // eyes-free hides the pitch; the other modes leave the choice to the "Hide pitch" button
  setBlind(eyes);
  $("L_callout").checked = calloutsWanted();
  renderSettingsSum();
}
// The closed Settings box says what is chosen: "Casual · ★ Northport" (or "No favourite club").
function renderSettingsSum() {
  const c = league && favClub && league.clubs[favClub];
  $("settingsSum").textContent = [t("mode_" + mode), c ? `★ ${c.name}` : t("sumNoClub")].join(" · ");
}
function applyI18n() {
  document.documentElement.lang = uiLang;
  if (live.ws && live.ws.readyState === 1) live.ws.send(JSON.stringify({ type: "set_lang", lang: lang() }));  // the commentator's voice
  const busy = live.ws || tour.on;
  document.querySelectorAll("[data-i18n]").forEach(e => { if (!(e.id === "captionMain" && busy)) e.textContent = t(e.dataset.i18n); });
  if (!busy) { $("captionMain").lang = uiLang; $("captionSub").hidden = true; }
  if (captionWaiting && !tour.on) idleCaption();
  document.querySelectorAll("[data-i18n-aria]").forEach(e => e.setAttribute("aria-label", t(e.dataset.i18nAria)));
  $("uiLangSel").value = uiLang;
  $("playBtn").textContent = live.ws ? t("stop") : t("idle");
  if (!live.ws) $("status").textContent = readyLine();
  setTeamNames(); fillClub(); fillMatches();
  if (live.ws && live.teams) renderStatus();
  fillFav(live.teams || (curMatch() ? curMatch().teams : null));
  renderLog(); renderRecap(); pickVoices(); live.marks.forEach(renderMark); renderWhy(); renderStats(); renderTourBtn(); setRecapBusy(!!recapWait);
  renderTimeline(); renderFeed();
}
// Either language changes from the next sentence on; the one being spoken finishes and nothing restarts.
// While listening, the status line (read aloud) says the commentator follows within the delay; stopped, it shows the ready line.
$("uiLangSel").addEventListener("change", e => {
  uiLang = e.target.value; store.set("htg.lang", uiLang); applyI18n(); preloadCallouts();
  if (live.ws) $("status").textContent = t("langSwitched");
});
// The delay is fixed per session (20 s in the fan modes, none in Analyst), so crossing between Analyst and a fan mode while listening
// restarts where the listener is, in the new mode (Highlights: the clip under way); otherwise a session started in Analyst would stay
// without the live commentator.
// remember: false for the listening view's Audio only, so htg.mode keeps the desk's own choice.
function setMode(m, remember = true) {
  const was = mode;
  mode = m; if (remember) store.set("htg.mode", mode); applyMode(); sendMode();
  if (live.ws && (was === "analyst") !== (mode === "analyst")) { const at = playT(); stopListening(); connect(at ?? startT); }  // the caption starts over: the old line belongs to the other delay
}
document.querySelectorAll("#modes button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
$("club").addEventListener("change", e => { favClub = e.target.value; store.set("htg.club", favClub); fillClub(); fillMatches(); sendClub(); });
// A new match or a new way to watch stops listening and waits for Start (from kick-off / the first clip): looking through the
// list, or an arrow key on the focused picker, must not start a match. The status line (read aloud) says what is ready. A timeline
// click, a moment and Next moment do start at once: they say "listen from here".
function readyFor() {
  if (live.ws) stopListening();
  $("status").textContent = readyLine();
}
$("matchBtn").addEventListener("click", () => openMatches($("matchList").hidden));
$("matchList").addEventListener("click", e => { const b = e.target.closest("button"); if (b) (view === "listen" ? listenPick : pickMatch)(b.dataset.id); });
$("mpick").addEventListener("keydown", e => { if (e.key === "Escape" && !$("matchList").hidden) { e.stopPropagation(); openMatches(false); $("matchBtn").focus(); } });
document.addEventListener("click", e => { if (view === "desk" && !$("matchList").hidden && !$("mpick").contains(e.target)) openMatches(false); });
document.querySelectorAll("#watch button").forEach(b => b.addEventListener("click", () => {
  if (watch === b.dataset.watch) return;
  if (live.ws) stopListening();
  watch = b.dataset.watch; store.set("htg.watch", watch); startT = 0;
  resetLive(); applyWatch(); readyFor();  // the other way to watch starts a new feed (resetLive clears it)
}));
$("tlTrack").addEventListener("click", e => {
  if (e.target.closest(".mk")) return;
  const r = $("tlInner").getBoundingClientRect();
  jumpTo(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * matchLen());
});
$("nextBtn").addEventListener("click", nextMoment);
$("recapBtn").addEventListener("click", askRecap);
document.querySelectorAll("#statsWin button").forEach(b => b.addEventListener("click", () => { live.statsWin = b.dataset.win; renderStats(); }));
// Space starts and stops listening, except while typing or choosing in a field. Handled on keydown; the keyup is swallowed so a
// focused button does not also get clicked.
const typing = el => el && (el.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName));
let spaceHandled = false;
document.addEventListener("keydown", e => {
  if (e.code !== "Space" || typing(e.target)) return;
  e.preventDefault(); spaceHandled = true;
  if (!e.repeat) $("playBtn").click();
});
document.addEventListener("keydown", e => {
  if (e.code !== "KeyN" || e.repeat || e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
  e.preventDefault(); nextMoment();
});
document.addEventListener("keyup", e => { if (e.code === "Space" && spaceHandled) { e.preventDefault(); spaceHandled = false; } });
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = pickVoices;
// Install button (Chrome, Edge, Samsung Internet). The manifest is added only where the browser can offer the install prompt, so
// Safari keeps its own home-screen behaviour (apple-touch-icon, opens in Safari). The button sits last in the side column: no shift.
if ("onbeforeinstallprompt" in window) {
  const link = document.createElement("link"); link.rel = "manifest"; link.href = "manifest.webmanifest"; document.head.append(link);
  let installEvt = null;
  window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); installEvt = e; $("installBtn").hidden = false; });
  window.addEventListener("appinstalled", () => { installEvt = null; $("installBtn").hidden = true; });
  $("installBtn").addEventListener("click", async () => {
    if (!installEvt) return;
    const e = installEvt; installEvt = null; $("installBtn").hidden = true;
    e.prompt(); await e.userChoice.catch(() => null);
  });
}
// A hidden tab stops listening (the client closes the socket, the server stops the session and its commentator) once nobody can hear
// it: 2 minutes after the browser suspended its audio (iOS lock screen, a frozen background tab). Listening with the screen locked is
// the point of the app, so a hidden tab whose sound still plays keeps going, up to 45 minutes, so a forgotten tab does not call
// Foundry for a whole match. Start picks up where it stopped. Checked every 10 s (hidden tabs may run timers less often).
const SILENT_STOP_MS = 2 * 60000, HIDDEN_STOP_MS = 45 * 60000;
let hiddenCheck = null;
function stopHidden() {
  const at = playT();
  stopListening(at === null ? undefined : `${t("pausedHidden")} ${clock(at)}.`);
}
document.addEventListener("visibilitychange", () => {
  clearInterval(hiddenCheck); hiddenCheck = null;
  if (!document.hidden || !live.ws) return;
  const hiddenAt = Date.now();
  let silentAt = null;
  hiddenCheck = setInterval(() => {
    if (!document.hidden || !live.ws) { clearInterval(hiddenCheck); hiddenCheck = null; return; }
    const now = Date.now();
    silentAt = ctx && ctx.state === "running" ? null : silentAt ?? now;
    if ((silentAt !== null && now - silentAt >= SILENT_STOP_MS) || now - hiddenAt >= HIDDEN_STOP_MS) {
      clearInterval(hiddenCheck); hiddenCheck = null; stopHidden();
    }
  }, 10000);
});
if (location.protocol.startsWith("http")) {
  fetch("matches.json").then(r => r.ok ? r.json() : null).then(j => {
    if (!j || !j.matches || !j.matches.length) return;
    league = j; matchId = curMatch().id;
    applyMatch();
  }).catch(() => {});
}
// Phones: the transport row is fixed to the bottom; its real height (font size, safe area, two-line labels) sets the page's bottom
// padding, so the last panel (Settings) is never under it.
if ("ResizeObserver" in window) new ResizeObserver(() => document.body.style.setProperty("--bar-h", $("controls").offsetHeight + "px")).observe($("controls"), { box: "border-box" });  // padding too: the safe area is padding
applyMode(); applyWatch(); applyI18n(); syncLiveRegions(); renderFeed();
requestAnimationFrame(loop);
