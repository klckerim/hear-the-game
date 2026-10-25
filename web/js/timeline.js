// Evidence timeline, including the Why card.
/* ---------------- evidence timeline ---------------- */
// Markers appear when their match time is played. A shot or goal marker carries the chance/goal Insight that rests on its event seq;
// tactical Insights get their own diamond. Danger-only chances are left out: they are never spoken (the sound carries danger).
// The axis is the whole match (0'-90', half-time tick). Bands: what the session plays (Live: from the start minute; Highlights: the
// clips). The match's known moments (goals, saved shots, cards) show from the start as buttons that start 30 s before them; a click
// on the track starts Live from that minute.
const HL_S = 6;
function at(a, fn) { const gen = live.gen; setTimeout(() => { if (live.gen === gen) fn(); }, Math.max(0, (a - ctx.currentTime) * 1000)); }
const matchLen = () => (isFinite(live.dur) && live.dur) || (curMatch() && curMatch().duration_s) || 5400;
const pct = tm => Math.min(100, Math.max(0, 100 * tm / matchLen()));
function renderTimeline() { renderAxis(); renderBands(); renderMoments(); renderNextBtn(); }
function renderAxis() {
  const ax = $("tlAxis"); ax.replaceChildren();
  for (let k = 0; k <= 6; k++) {
    const s = document.createElement("span");
    s.textContent = k * 15 + "'"; s.style.left = pct(k * 900) + "%"; s.className = k === 3 ? "ht" : ""; ax.append(s);
  }
}
function plannedWindows() {  // Highlights: every clip of the match (also the ones before the clip under way)
  if (watch === "highlights") return allClips();
  return live.ws && live.windows ? live.windows : [[startT, matchLen()]];
}
function renderBands() {
  const inner = $("tlInner"); inner.querySelectorAll(".tl-band").forEach(e => e.remove());
  for (const [a, b] of plannedWindows()) {
    const d = document.createElement("div"); d.className = "tl-band";
    d.style.left = pct(a) + "%"; d.style.width = (pct(b) - pct(a)) + "%"; inner.prepend(d);
  }
}
function renderMoments() {
  const inner = $("tlInner"); inner.querySelectorAll(".mk.mo").forEach(e => e.remove());
  for (const mo of moments()) {
    const b = document.createElement("button"), parts = [t("mo_" + mo.kind), clock(mo.t), uiTeam(mo.team), t(watch === "highlights" ? "playClip" : "startBefore")];
    b.type = "button"; b.className = "mk mo " + mo.kind; b.style.left = pct(mo.t) + "%"; b.style.setProperty("--c", teamColor(mo.team));
    b.setAttribute("aria-label", parts.join(", ")); b.title = parts.join(" · ");
    b.addEventListener("click", () => jumpTo(mo.t - 30));
    inner.append(b);
  }
  const g = moments().find(mo => mo.kind === "goal");  // a hint, not a button: where the first goal is
  $("tlHint").textContent = g && !live.ws ? t("tlHint").replace("{m}", Math.floor(g.t / 60) + 1) : "";
}
// The match before the session's start (or between Highlights clips): its Insights and shots / goals, drawn at once and selectable
// for their evidence, without the "new" flash.
function addHistory(items) {
  for (const h of items || []) {
    if (h.type === "insight") addInsight(h, true);
    else if ((h.kind === "shot" && h.outcome !== "goal") || h.kind === "goal") addEventMark(h);
  }
}
function addInsight(m, quiet = false) {
  const ins = m.insight;
  if (ins.claim_facts.source === "danger") return;
  if (ins.type === "goal" || ins.type === "chance") {  // belongs to its shot or goal marker, whichever exists first
    const mk = live.marks.find(k => k.kind !== "ins" && ins.evidence.includes(k.seq));
    if (mk) { mk.ins = m; renderMark(mk); } else ins.evidence.forEach(s => { live.insBySeq[s] = m; });
    return;
  }
  const mk = addMark({ kind: "ins", t: ins.t, team: ins.team, ins: m });
  if (!quiet) { mk.el.classList.add("new"); setTimeout(() => mk.el.classList.remove("new"), 2800); }  // the system "noticing" something
}
function addEventMark(m) {
  addMark({ kind: m.kind, t: m.t, team: m.team, seq: m.seq, x: m.x, y: m.y, player_id: m.player_id, outcome: m.outcome,
    speed: m.speed_mps, ins: live.insBySeq[m.seq] || null });
}
function addMark(mk) {
  const b = mk.el = document.createElement("button");
  b.type = "button"; b.className = "mk " + mk.kind; b.setAttribute("aria-pressed", "false");
  b.style.left = pct(mk.t) + "%"; b.style.setProperty("--c", teamColor(mk.team));
  // e.detail: a pointer click (a keyboard click is 0 and keeps its own marker; Tab reaches each one)
  b.addEventListener("click", e => selectMark(e.detail && live.sel === mk ? nextOverlap(mk) : mk));
  live.marks.push(mk); $("tlInner").append(b); renderMark(mk);
  return mk;
}
// Markers of one lane closer than their 22 px hit area cover each other, and the newest is on top. The selected one is raised
// (CSS), so a second tap on it selects the next overlapping one, in match order, and round again.
function nextOverlap(mk) {
  const lane = k => k.kind === "ins", x = k => k.el.offsetLeft;
  const near = live.marks.filter(k => lane(k) === lane(mk) && Math.abs(x(k) - x(mk)) < 22).sort((p, q) => p.t - q.t);
  return near[(near.indexOf(mk) + 1) % near.length];
}
function markSpoken(m) {
  const mk = live.marks.find(k => k.ins && k.ins.insight.insight_id === m.insight_id);
  if (!mk) return;
  mk.speech = m; renderMark(mk);
  if (live.sel === mk) renderWhy();
}
// A side's club in the current match: from the session's hello, else from the fixture list (before Start), else none (run_local).
const teamInfo = side => live.teams ? live.teams[side] : curMatch() ? curMatch().teams[side] : null;
function uiTeam(side) { const i = teamInfo(side); return i ? i["name_" + uiLang] : t(side === "HOME" ? "home" : "away"); }
function insTitle(ins) {
  const f = ins.claim_facts, tpl = t("ins_" + ins.type) || ins.type;
  return tpl.replace("{team}", f["team_" + uiLang] || "").replace("{player}", f.player || "").replace("{side}", (uiLang === "tr" ? f.side_tr : f.side) || "");
}
function markParts(mk) {
  if (mk.kind === "ins") return [t("tlInsight"), clock(mk.t), insTitle(mk.ins.insight) + (mk.speech ? ` (${t("spoken")})` : "")];
  const who = live.players[mk.player_id];
  return [mk.kind === "goal" ? t("tlGoal") : t("tlShot"), clock(mk.t), uiTeam(mk.team), ...(who ? [who] : []),
    ...(mk.kind === "shot" && mk.outcome ? [t("outcome")[mk.outcome] || mk.outcome] : [])];
}
function renderMark(mk) {
  const parts = markParts(mk);
  mk.el.setAttribute("aria-label", parts.join(", ")); mk.el.title = parts.join(" · ");
  mk.el.classList.toggle("spoken", !!mk.speech);
}
function selectMark(mk) {
  live.sel = mk; live.hl = { mk, at: performance.now() };
  live.marks.forEach(k => k.el.setAttribute("aria-pressed", String(k === mk)));
  renderWhy();
}
// claim_facts as key/value pairs in the interface language: "team_en" shows as "team" in English, "side_tr" as "side" in Turkish.
function factPairs(f) {
  const out = [];
  for (const [k, v] of Object.entries(f)) {
    const m = k.match(/^(.*)_(en|tr)$/);
    if (m ? m[2] !== uiLang : (uiLang === "tr" && (k + "_tr") in f)) continue;
    out.push([(m ? m[1] : k).replace(/_/g, " "), String(v)]);
  }
  return out;
}
function renderWhy() {
  const mk = live.sel, dl = $("whyFacts");
  dl.replaceChildren();
  $("why").hidden = !mk;  // only when a marker is selected
  if (!mk) {
    $("whyTitle").textContent = t("whyTitle"); $("whyMain").textContent = t("whyIdle"); $("whyMain").lang = uiLang;
    $("whySub").hidden = $("whyTag").hidden = dl.hidden = $("whyEvidence").hidden = true;
    return;
  }
  $("whyTitle").textContent = markParts(mk).join(" · ");
  const ins = mk.ins && mk.ins.insight, text = mk.speech ? mk.speech.text : mk.ins ? mk.ins.text : null;
  const main = text && text[lang()] !== undefined ? lang() : uiLang, sub = text && main !== uiLang ? text[uiLang] : undefined;  // caption rules
  $("whyMain").textContent = text ? text[main] : ""; $("whyMain").lang = main;
  $("whySub").textContent = sub || ""; $("whySub").lang = uiLang; $("whySub").hidden = !sub;
  const src = mk.speech && mk.speech.source && mk.speech.source[lang()];
  $("whyTag").hidden = !text;
  $("whyTag").textContent = mk.speech ? TAG[uiLang][src || "template"] : `${TAG[uiLang].template} · ${t("notSpoken")}`;
  $("whyTag").classList.toggle("dim", !mk.speech || src === "template");
  const pairs = ins ? factPairs(ins.claim_facts) : [];
  if (mk.speed) pairs.push([t("speed"), `${Math.round(mk.speed * 3.6)} ${t("kmh")}`]);
  for (const [k, v] of pairs) {
    const d = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = k; dd.textContent = v; d.append(dt, dd); dl.append(d);
  }
  dl.hidden = !pairs.length;
  $("whyEvidence").hidden = !ins;
  if (ins) $("whyEvidence").textContent = `${t("evidence")}: ${ins.evidence.length} ${t(ins.evidence.length === 1 ? "event" : "events")}`;
}
function drawEvidence(g, sx, sy, dpr) {
  const hl = live.hl; if (!hl) return;
  const age = (performance.now() - hl.at) / 1000;
  if (age > HL_S) { live.hl = null; return; }
  g.globalAlpha = Math.min(1, (HL_S - age) / 1.5);  // fades over the last 1.5 s
  const mk = hl.mk, m = mk.ins, z = m && m.zone;
  if (z && mk.kind === "ins") { g.fillStyle = "rgba(242,179,61,0.16)"; g.fillRect(sx(z.x[0]), sy(z.y[1]), sx(z.x[1]) - sx(z.x[0]), sy(z.y[0]) - sy(z.y[1])); }
  const dot = (x, y, r, side) => {
    g.beginPath(); g.arc(sx(x), sy(y), r * dpr, 0, Math.PI * 2); g.fillStyle = teamColor(side); g.fill();
    g.lineWidth = 1.5 * dpr; g.strokeStyle = "#f5f7f5"; g.stroke();
  };
  if (mk.kind !== "ins" && mk.x !== undefined) {  // shot or goal: where it was struck, and a line to the goal it aimed at
    g.setLineDash([6 * dpr, 5 * dpr]); g.lineWidth = 2 * dpr; g.strokeStyle = "#f5f7f5";
    g.beginPath(); g.moveTo(sx(mk.x), sy(mk.y)); g.lineTo(sx(mk.team === "HOME" ? 105 : 0), sy(34)); g.stroke(); g.setLineDash([]);
    dot(mk.x, mk.y, 7, mk.team);
  } else if (m) m.evidence_points.forEach(p => dot(p.x, p.y, 4.5, p.team));
  g.globalAlpha = 1;
}
function drawTimeline() {
  const r = live.ws && live.cur, on = !!r;
  $("tlNow").hidden = !on;
  $("tlPast").style.width = on ? `calc(${pct(r.t)}% + 12px)` : "0";
  if (on) $("tlNow").style.left = pct(r.t) + "%";
}

