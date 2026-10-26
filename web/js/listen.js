// The listening view and the switch to the desk.
/* ---------------- views ---------------- */
// One page, two views of the same session: the listening view (the first screen, for fans who listen rather than look) and the
// desk (pitch, timeline, feed, panels). body[data-view] decides what shows. A switch never stops the sound; it changes the mode
// only when it differs: the listening view always plays in Audio only, the desk in the listener's own mode, which htg.mode keeps
// (the forced Audio only is never stored). Opens the stored view; first visit: listen; ?view=listen|desk overrides and is stored.
const VIEWS = ["listen", "desk"];
let view = (() => {
  const q = new URLSearchParams(location.search).get("view");
  if (VIEWS.includes(q)) { store.set("htg.view", q); return q; }
  return VIEWS.includes(store.get("htg.view")) ? store.get("htg.view") : "listen";
})();
document.body.dataset.view = view;
if (view === "listen") mode = "eyes_free";  // before main.js applies the mode
const deskMode = () => MODES.includes(store.get("htg.mode")) ? store.get("htg.mode") : "casual";
function setView(v) {
  view = v; store.set("htg.view", v); document.body.dataset.view = v; arrange();
  const want = v === "listen" ? "eyes_free" : deskMode();
  if (want !== mode) setMode(want, false);
  if (live.ws && live.teams) renderStatus();  // the delay shows in the desk only
}
function viewBtn(id, to) {
  const b = document.createElement("button");
  b.type = "button"; b.id = id; b.dataset.i18n = id;
  b.addEventListener("click", () => { setView(to); $(to === "listen" ? "playBtn" : "toListen").focus(); });  // the pressed button is gone
  return b;
}
// The listening view's own elements; the rest are the desk's. DOM order is the reading and the visual order: title, tagline,
// the "now playing" card (score, clock, caption), Start, Next moment and Catch me up, Live / Highlights, status, the match list,
// tour offer, a hint (CSS shows the lock-screen one on touch screens, the keys elsewhere; the other is display: none), the switch.
const el = (tag, cls, key) => { const e = document.createElement(tag); e.className = cls; if (key) e.dataset.i18n = key; return e; };
document.querySelector("h1").after(el("p", "l-sub listen-only", "listenSub"));
// No language control here (owner, 2026-10-27: switching in this view mixed VoiceOver's voices): it follows the device language or
// ?lang; the desk's select changes it for both views.
const listenMore = el("div", "l-more listen-only"), chooseTitle = el("h2", "", "chooseMatch"), keys = el("p", "l-hint l-keys", "keysLine");
chooseTitle.id = "chooseTitle";
listenMore.append(chooseTitle, keys, el("p", "l-hint l-touch", "touchLine"), viewBtn("toDesk", "desk"));
document.querySelector(".d-now").after(listenMore);
$("appLang").before(viewBtn("toListen", "listen"));  // desk header, beside the language: not in the phone player bar
// A few desk elements move into the listening view's order and back; a comment marks each one's place in the desk.
const homes = new Map();
function moveTo(e, put) { if (!homes.has(e)) { const mark = document.createComment(e.id); e.before(mark); homes.set(e, mark); } put(e); }
function arrange() {
  if (view === "listen") {
    moveTo($("caption"), e => document.querySelector(".scorebar").after(e));  // into the card
    moveTo($("watch"), e => $("recapBtn").after(e));
    moveTo($("matchList"), e => chooseTitle.after(e));
    moveTo($("tourBanner"), e => keys.before(e));
    $("matchList").hidden = false;  // always open: VoiceOver swipes straight through it
  } else {
    homes.forEach((mark, e) => mark.after(e));
    $("matchList").hidden = true; $("matchBtn").setAttribute("aria-expanded", "false");
  }
}
arrange();
// A match card starts that match at once (Live from kick-off, or Highlights); swiping through the list activates nothing. Same start
// path as Start, synchronously in the tap (iOS unlocks audio only inside the gesture). The match already playing only moves focus.
function listenPick(id) {
  if (id !== curMatch().id) setMatch(id);
  if (!live.ws) { endTour(); connect(); }
  $("playBtn").focus();
}
