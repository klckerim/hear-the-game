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
  view = v; store.set("htg.view", v); document.body.dataset.view = v;
  const want = v === "listen" ? "eyes_free" : deskMode();
  if (want !== mode) setMode(want, false);
}
function viewBtn(id, to) {
  const b = document.createElement("button");
  b.type = "button"; b.id = id; b.dataset.i18n = id;
  b.addEventListener("click", () => { setView(to); $(to === "listen" ? "playBtn" : "toListen").focus(); });  // the pressed button is gone
  return b;
}
// The listening view's own elements; the rest are the desk's, shown or hidden by app.css.
const listenMore = document.createElement("section");
listenMore.className = "listen-only"; listenMore.id = "listenMore";
listenMore.append(viewBtn("toDesk", "desk"));
document.querySelector(".d-now").after(listenMore);
$("appLang").before(viewBtn("toListen", "listen"));  // desk header, beside the language: not in the phone player bar
