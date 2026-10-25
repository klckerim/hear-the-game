// Live stream: session start, resetLive, Highlights cut, analyst log, recap / What did I miss.
/* ---------------- live stream ---------------- */
// Match clock -> audio clock: audioTime = clock0 + matchT / speed. Everything the server sends carries a match time.
const live = { ws: null, clock0: null, speed: 1, teams: null, frames: [], due: [], score: [0, 0], lastTickSlot: -1, nextBeat: 0, cur: null, log: [], recap: [], favT: -99,
  gen: 0, marks: [], insBySeq: {}, players: {}, sel: null, hl: null, windows: null, stats: null, statsWin: "match", feed: [] };
const matchNow = () => (ctx.currentTime - live.clock0) * live.speed;
const audioAt = t => Math.max(ctx.currentTime, live.clock0 + t / live.speed);

// Live: from `from` (match seconds) to full time. Highlights: the clips not yet over at `from` (0: all of them).
function connect(from = startT) {
  startT = Math.max(0, Math.floor(from));
  initAudio(); ctx.resume();
  primeVoice(); preloadCallouts();
  resetLive();
  session = newSession(); applyLayers();
  $("playBtn").textContent = t("stop");
  $("status").textContent = t("wait");
  const delay = mode === "analyst" ? "" : `&delay=${DELAY_S}`;
  const q = `match=${encodeURIComponent(matchId || "")}&mode=${watch}&from=${startT}`;
  const ws = live.ws = new WebSocket(WS_URL + (WS_URL.includes("?") ? "&" : "?") + q + delay + "&lang=" + lang());
  ws.onmessage = e => onMessage(JSON.parse(e.data));
  ws.onclose = () => { if (live.ws === ws) { stopListening(t("lost")); } };
  ws.onerror = () => { if (live.ws === ws) { stopListening(t("fail")); } };
  live.timer = setInterval(schedule, 25);
}
function stopListening(msg) {
  const ws = live.ws; live.ws = null;
  if (ws) { ws.onclose = ws.onerror = null; ws.close(); }
  clearInterval(live.timer); endSession(session); session = null; stopSpeech();
  $("playBtn").textContent = t("idle"); $("status").textContent = msg || t("off"); renderTimeline();
}
// A timeline click, a moment marker and Next moment start listening at once, in the way to watch the listener chose. Live: from that
// match second (Next moment: 30 s before the next goal, saved shot or card more than 30 s after the play clock, or after the chosen
// start when stopped). Highlights: the clip at or after that second (the last clip if none is left); Next moment = the next clip.
// The server plays Highlights from `from` as the clips not over yet, so a clip always starts at its beginning.
const playT = () => live.ws && live.cur ? live.cur.t : null;
const moments = () => live.moments || (curMatch() ? curMatch().moments : []);
const allClips = () => (curMatch() && curMatch().windows) || live.windows || [];
function nextMomentT() { const from = playT() ?? startT, m = moments().find(mo => mo.t > from + 30); return m ? m.t : null; }
function clipFrom(t) { const c = allClips(), w = c.find(w => w[1] > t) || c[c.length - 1]; return w ? w[0] : t; }
function nextTarget() {
  if (watch === "highlights") { const from = playT() ?? startT - 1, w = allClips().find(w => w[0] > from + 1); return w ? w[0] : null; }
  const tm = nextMomentT();
  return tm === null ? null : tm - 30;
}
function renderNextBtn() { $("nextBtn").disabled = nextTarget() === null; }
function nextMoment() { const t = nextTarget(); if (t !== null) jumpTo(t); }
function jumpTo(t) {
  endTour();
  if (live.ws) stopListening();
  connect(watch === "highlights" ? clipFrom(t) : t);
}
// The status is read aloud: match, Live from a minute or Highlights, and in the fan modes "Live commentary · 20 s delay". Redrawn on
// a language change.
function renderStatus() {
  let s = `${uiTeam("HOME")} – ${uiTeam("AWAY")}`;
  if (live.watch === "highlights") s += ` · ${t("watchHl")} · ${(live.moments || []).length} ${t("hlCount")}`;
  else s += ` · ${startT >= 60 ? `${t("liveFrom")} ${Math.floor(startT / 60)}'` : t("watchLive")}`;
  if (live.delay_s) s += ` · ${live.commentary ? t("liveDelay") + " · " : ""}${live.delay_s} ${t("secs")} ${t("delayWord")}`;
  $("status").textContent = s;
}
// A new session (any start) resets what belongs to its window. The commentary feed is what the listener has heard of this match: it
// stays across jumps within the match (Next moment, a timeline click, a mode switch) and goes when the match changes.
function resetLive() {
  const feed = live.feedMatch === matchId ? live.feed : [];
  Object.assign(live, { clock0: null, frames: [], due: [], score: [0, 0], lastTickSlot: -1, nextBeat: 0, cur: null, log: [], recap: [], recapOut: null, ended: false,
    gen: live.gen + 1, marks: [], insBySeq: {}, sel: null, hl: null, windows: null, stats: null, delay_s: 0, commentary: false, feed, feedMatch: matchId,
    cutShow: null, trail: [] });
  $("tlInner").querySelectorAll(".mk:not(.mo)").forEach(e => e.remove()); renderTimeline(); renderWhy(); renderStats(); renderFeed();
  clearTimeout(recapWait); recapWait = null; setRecapBusy(false);
  $("score").textContent = "0 – 0"; renderLog(); live.recap = []; renderRecap(); live.favT = -99;
  Object.assign(callouts, { cur: null, lastA: -99, nameT: -99, held: 0 });
}

function onMessage(m) {
  if (m.type === "hello") {
    live.speed = m.speed || 1; live.teams = m.teams; live.windows = m.windows || null; live.dur = m.duration_s || Infinity;
    live.moments = m.moments || null; live.watch = m.watch || "live"; renderTimeline();
    live.players = Object.fromEntries(["HOME", "AWAY"].flatMap(s => m.teams[s].players.map(p => [p.id, p.name])));
    for (const [side, id] of [["HOME", "Home"], ["AWAY", "Away"]]) {
      $("dot" + id).style.background = COLOR[m.teams[side].color] || "#ccc";
    }
    if (m.score) { live.score = [m.score.HOME || 0, m.score.AWAY || 0]; $("score").textContent = live.score.join(" – "); }
    Object.assign(live, { delay_s: m.delay_s || 0, commentary: !!m.commentary }); renderStatus();
    fillFav(m.teams); setTeamNames(); fillClub(); sendMode(); sendClub();
    addHistory(m.history);
  } else if (m.type === "state") {
    if (live.clock0 === null) live.clock0 = ctx.currentTime + JITTER_S - m.packets[0].t / live.speed;
    if (!live.windows) { live.windows = [[m.packets[0].t, matchLen()]]; renderTimeline(); }  // run_local sends no windows
    live.frames.push(...m.packets);
  } else if (m.type === "event_cue") {
    live.due.push({ t: m.t, kind: "cue", m });
  } else if (m.type === "stats") {
    live.due.push({ t: m.t, kind: "stats", m });
  } else if (m.type === "commentary") {
    live.due.push({ t: m.t, kind: "comm", m });
  } else if (m.type === "insight") {
    live.due.push({ t: m.insight.t, kind: "insight", m });
  } else if (m.type === "speech") {
    live.due.push({ t: m.t, kind: "speech", m });
  } else if (m.type === "cut") {  // Highlights: the clip ends at t_from, the next one starts at t_to
    live.due.push({ t: m.t_from, kind: "cut", m });
  } else if (m.type === "recap") {
    if (m.kind === "full_time" || m.kind === "half_time") { live.due.push({ t: m.t, kind: "recap", m }); return; }  // plays when its match time arrives
    clearTimeout(recapWait); recapWait = null; setRecapBusy(false); playRecap(m);
  }
}

function schedule() {
  if (live.clock0 === null) return;
  const mt = matchNow(), horizon = mt + 0.12 * live.speed, L = session.L;
  // 10 Hz packets -> ~8 ticks per second, plus the pressure pulse
  while (live.frames.length && live.frames[0].t < horizon) {
    const r = live.frames.shift(), a = audioAt(r.t), late = a - live.clock0 - r.t / live.speed > 0.05;
    live.cur = r; live.trail = (live.trail || []).concat(r).slice(-15);
    const slot = Math.floor(r.t / 0.125);
    if (r.in_play && slot !== live.lastTickSlot && !late) sndTick(L.ball, a, r.team, r.danger, r.pan, 0.12 + 0.12 * r.tempo);
    live.lastTickSlot = slot;
    if (r.in_play && r.pressure > 0.15 && a >= live.nextBeat && !late) { sndBeat(L.press, a, 0.35 + 0.5 * r.pressure); live.nextBeat = a + 1 / (0.9 + 2.3 * r.pressure); }
    session.crowdGain.gain.setTargetAtTime(0.03 + 0.12 * r.danger, ctx.currentTime, 0.5);
  }
  live.due.sort((x, y) => x.t - y.t);
  while (live.due.length && live.due[0].t < horizon) {
    const d = live.due.shift(), m = d.m;
    if (d.kind === "cut") { cutTo(m); break; }  // the play clock jumps; the next clip's items are due from the next tick
    const a = audioAt(m.t);
    if (d.kind === "cue") cue(m, a);
    else if (d.kind === "insight") at(a, () => addInsight(m));
    else if (d.kind === "recap") at(a, () => { if (live.ws) playRecap(m); });
    else if (d.kind === "stats") at(a, () => { live.stats = m; renderStats(); renderNextBtn(); });
    else if (d.kind === "comm") commentaryLine(m, a);
    else speech(m, a);
  }
}
// Highlights transition: a soft whoosh, the next clip's minute on the pitch (and read in the status line), then the clip ~1.2 s later.
// The score comes from the server's warm-up; nothing is recomputed here.
const CUT_GAP_S = 1.2;
function cutTo(m) {
  const now = ctx.currentTime;
  live.clock0 = now + CUT_GAP_S - m.t_to / live.speed;
  Object.assign(live, { lastTickSlot: -1, nextBeat: 0, trail: [], cutShow: { text: `${Math.floor(m.t_to / 60)}'`, at: performance.now() } });
  if (m.score) { live.score = [m.score.HOME || 0, m.score.AWAY || 0]; $("score").textContent = live.score.join(" – "); }
  addHistory(m.history);
  const f = sndNoise(session.L.cue, now, 0.9, "bandpass", 350, 0.8, 0.22, 0, 0.45);
  f.frequency.exponentialRampToValueAtTime(2400, now + 0.8);
  $("status").textContent = `${t("cutTo")} ${Math.floor(m.t_to / 60)}'`;
}
function cue(m, a) {
  const L = session.L.cue, k = m.kind;
  if (["pass", "restart"].includes(k)) sndClick(L, a, m.pan);
  else if (k === "shot") sndWhoosh(L, a - 0.1, m.pan);
  else if (k === "save") sndThud(L, a, m.pan);
  else if (k === "foul" && m.card) { sndWhistle(L, a + 0.1, 0.25, 0.05); sndWhistle(L, a + 0.45, 0.9, 0.06); }  // booking: short + long, louder
  else if (["out", "foul"].includes(k)) sndWhistle(L, a + 0.1, 0.4, 0.04);
  else if (k === "kickoff") sndWhistle(L, a, 0.7, 0.05);
  else if (k === "period_end") {  // two short whistles at half-time; two short and a long one at full time
    sndWhistle(L, a, 0.3, 0.05); sndWhistle(L, a + 0.45, 0.3, 0.05);
    if (m.period === 2) {
      sndWhistle(L, a + 0.9, 1.1, 0.05);
      at(a, () => { live.ended = true; });
    }
    addLog(Math.ceil(m.t), null, m.period === 2 ? t("fullTimeLog") : t("halfTimeLog"), a);
  }
  else if (k === "goal") { sndGoal(L, a, m.team, !club ? "neutral" : m.team === club ? "for" : "against"); live.score[m.team === "HOME" ? 0 : 1]++; $("score").textContent = live.score.join(" – "); }
  if ((k === "shot" && m.outcome !== "goal") || k === "goal") at(a, () => addEventMark(m));  // the scoring shot shows as the goal
  const fav = $("fav").value && m.player_id === $("fav").value;
  if (fav) {  // the favourite player touched the ball: a two-note chime on the side the ball is on, at most every 3 s of match time
    if (m.t - live.favT > 3) { sndEarcon(L, a + 0.02, m.pan); live.favT = m.t; flashFav(); }
  }
  const label = logLabel(m);
  if (label) addLog(m.t, m.team, label + (fav ? " ★" : ""), a);
  callout(m, a);
}
// Analyst log line: shots with speed and outcome, goals with the scorer, cards with the player, passes only when long (> 30 m) with their length.
function logLabel(m) {
  const k = m.kind, who = live.players[m.player_id];
  if (k === "pass") return m.length_m > 30 ? [t("longPass"), who, `${Math.round(m.length_m)} m`].filter(Boolean).join(" · ") : null;
  if (k === "shot") return [LABEL[uiLang].shot, who, m.speed_mps ? `${Math.round(m.speed_mps * 3.6)} ${t("kmh")}` : "", m.outcome && t("outcome")[m.outcome]].filter(Boolean).join(" · ");
  if (k === "goal") return [LABEL[uiLang].goal, who].filter(Boolean).join(" · ");
  if (k === "foul" && m.card) return [LABEL[uiLang].foul, LABEL[uiLang][m.card], who].filter(Boolean).join(" · ");
  return LABEL[uiLang][k] || null;
}
function speech(m, a) {
  const text = m.text[lang()];
  live.recap.unshift({ t: m.t, text: m.text }); live.recap.length = Math.min(live.recap.length, 5); at(a, renderRecap);
  m.buf = { [lang()]: decodeClip(m, lang()) };  // decode ahead; the clip plays when its match time arrives
  at(a, () => { if (live.ws) say(m); });  // at(): dropped if the session changed meanwhile (new match, mode, jump)
  at(a, () => markSpoken(m));
  addLog(m.t, null, "🎙 " + text, a);
}
function decodeClip(m, l) {
  const b64 = m.audio && m.audio[l];
  if (!b64) return Promise.resolve(null);
  const bin = atob(b64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return ctx.decodeAudioData(bytes.buffer).catch(() => null);
}
function addLog(t, team, label, a) {
  at(a, () => { live.log.unshift({ t, team, label }); live.log.length = Math.min(live.log.length, 6); renderLog(); });
}
function renderLog() {
  const ol = $("log"); ol.replaceChildren();
  if (!live.log.length) { const li = document.createElement("li"); li.innerHTML = '<span class="empty"></span>'; li.firstChild.textContent = t("logEmpty"); ol.append(li); return; }
  for (const e of live.log) {
    const li = document.createElement("li"), tm = document.createElement("time"), dot = document.createElement("span"), tx = document.createElement("span");
    tm.textContent = clock(e.t); dot.className = "dot"; dot.style.cssText = `background:${e.team ? COLOR[live.teams[e.team].color] : "var(--muted)"};width:8px;height:8px`;
    tx.textContent = e.label; li.append(tm, dot, tx); ol.append(li);
  }
}
function renderRecap() {
  const ol = $("recap"); ol.replaceChildren();
  const r0 = live.recapOut;
  if (r0) {  // the latest agent (or template) recap, above the narration list
    const li = document.createElement("li"), b = document.createElement("b"), p = document.createElement("span");
    li.className = "out";
    b.textContent = r0.kind === "full_time" ? t("fullTime") : r0.kind === "half_time" ? t("halfTimeRecap") : `${t("recapTag")} · ${t("missedSince")} ${r0.since_min}${t("recapSince") ? " " + t("recapSince") : ""}`;
    p.textContent = r0.text[lang()].join(" "); p.lang = lang(); li.append(b, p);
    const sub = document.createElement("small"); sub.lang = uiLang; sub.hidden = lang() === uiLang; sub.textContent = r0.text[uiLang].join(" ");
    li.append(sub); ol.append(li);
  }
  if (!live.recap.length) { if (!r0) { const li = document.createElement("li"); li.className = "note"; li.textContent = t("recapEmpty"); ol.append(li); } return; }
  for (const r of live.recap) { const li = document.createElement("li"), tm = document.createElement("time"); tm.textContent = clock(r.t); li.append(tm, r.text[lang()]); ol.append(li); }
}
// "What did I miss?": the server's Recap agent writes 2-3 verified sentences (template recap if the agent fails). Without a server
// answer in RECAP_WAIT_MS, or before the match is connected, the old behaviour: score + the last three narrations.
const RECAP_WAIT_MS = 30000;
let recapWait = null;
function setRecapBusy(on) { const b = $("recapBtn"); b.textContent = on ? t("preparing") : t("recapBtn"); b.setAttribute("aria-busy", String(on)); }
function askRecap() {
  if (!(live.ws && live.ws.readyState === 1 && live.teams)) { readRecap(); return; }
  if (recapWait) return;
  live.ws.send(JSON.stringify({ type: "recap_request" }));
  setRecapBusy(true);
  recapWait = setTimeout(() => { recapWait = null; setRecapBusy(false); readRecap(); }, RECAP_WAIT_MS);
}
function playRecap(m) {
  live.recapOut = m; renderRecap();
  const joined = { en: m.text.en.join(" "), tr: m.text.tr.join(" ") };
  say({ text: joined, source: m.source, audio: m.audio, team: null }, m.kind === "full_time" ? t("fullTime") : m.kind === "half_time" ? t("halfTimeRecap") : t("recapTag"));
}
// The old "What did I miss": speak the score and the last three narrations, oldest first, with the device voice
function readRecap() {
  if (!live.recap.length) { setCaption({ [uiLang]: t("recapEmpty") }, false); return; }
  const said = l => [`${T[l].recapScore}: ${live.score.join(" - ")}.`, ...live.recap.slice(0, 3).reverse().map(r => r.text[l])];
  const lines = said(lang());
  setCaption({ [lang()]: lines.join(" "), [uiLang]: said(uiLang).join(" ") }, true); $("captionTag").textContent = t("recapTitle");
  const v = voiceFor[lang()];
  if ("speechSynthesis" in window && v) { speechSynthesis.cancel(); lines.forEach(l => { const u = new SpeechSynthesisUtterance(l); u.voice = v; u.lang = v.lang; u.rate = 1.05; speechSynthesis.speak(u); }); }
}
const clock = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

