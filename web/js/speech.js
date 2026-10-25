// Narration, callouts, live commentator and the feed.
/* ---------------- narration ---------------- */
let voiceFor = {}, fallbackTimer = null;
function pickVoices() {
  if (!("speechSynthesis" in window)) { $("voiceNote").textContent = t("novoice"); return; }
  const vs = speechSynthesis.getVoices();
  voiceFor.tr = vs.find(v => v.lang && v.lang.toLowerCase().startsWith("tr"));
  voiceFor.en = vs.find(v => /en[-_]gb/i.test(v.lang)) || vs.find(v => v.lang && v.lang.toLowerCase().startsWith("en"));
  $("voiceNote").textContent = voiceFor[lang()] ? `${t("voice")}: ${voiceFor[lang()].name} ${t("voiceTail")}` : t("novoice");
}
function primeVoice() { if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance("")); }  // unlock on the user gesture
// text: { en, tr }. Shows the commentary-language sentence; when the interface language differs and the message has it, that version
// sits under it in smaller muted text. A message with only one language shows that one (no translation in the client).
function setCaption(text, liveNow) {
  const main = text[lang()] !== undefined ? lang() : uiLang, sub = main !== uiLang ? text[uiLang] : undefined;
  $("captionMain").textContent = text[main] ?? ""; $("captionMain").lang = main;
  $("captionSub").textContent = sub ?? ""; $("captionSub").lang = uiLang; $("captionSub").hidden = !sub;
  $("captionTag").classList.toggle("idle", !liveNow);
}
function duckTo(v) { if (duck) duck.gain.setTargetAtTime(v, ctx.currentTime, 0.08); }
const TAG = { tr: { llm: "doğrulandı", agent: "doğrulandı", template: "şablon" }, en: { llm: "verified", agent: "verified", template: "template" } };
async function say(m, prefix) {
  const l = lang(), text = m.text[l];
  setCaption(m.text, true);
  $("captionTag").textContent = (prefix ? prefix + " · " : "") + TAG[uiLang][(m.source && m.source[l]) || "template"];
  $("captionMine").hidden = !(club && m.team === club);
  const finish = () => { duckTo(1); setTimeout(() => { $("captionTag").classList.add("idle"); $("captionMine").hidden = true; }, 400); };
  if (!$("L_voice").checked) return;
  // A callout already under way finishes first (at most ~2 s; "Goal! Rossi!", then the sentence): cutting the commentator off
  // mid-name sounded broken. New callouts wait while the sentence is pending.
  const wait = callouts.cur ? Math.min(3, callouts.cur.end - ctx.currentTime) : 0, gen = live.gen;
  if (wait > 0) {
    callouts.held++; await new Promise(r => setTimeout(r, wait * 1000 + 150)); callouts.held = Math.max(0, callouts.held - 1);
    if (live.gen !== gen) return;  // a new session (match, mode, jump) started meanwhile: this sentence or recap belongs to the old one
  }
  if (comm && comm.goal) {  // a goal line is never cut off; the sentence follows it (max 8 s)
    const end = Date.now() + 8000;
    while (comm && comm.goal && Date.now() < end) await new Promise(r => setTimeout(r, 150));
    if (live.gen !== gen) return;
  }
  stopCallout(); stopComm(); duckTo(0.3);
  const buf = await ((m.buf && m.buf[l]) || decodeClip(m, l));
  if (live.gen !== gen) { duckTo(1); return; }  // decoding took long enough for the listener to switch
  if (buf && ctx) {  // Azure clip from the server
    stopClip();
    const src = ctx.createBufferSource(); src.buffer = buf; src.connect(voiceBus);
    src.onended = () => { if (clip === src) { clip = null; finish(); } };
    clip = src; clipGoal = m.priority >= 5; src.start();
    return;
  }
  const v = voiceFor[l];
  if ("speechSynthesis" in window && v) {
    const u = new SpeechSynthesisUtterance(text);
    u.voice = v; u.lang = v.lang; u.rate = 1.05; u.onend = finish; u.onerror = finish;
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  } else { clearTimeout(fallbackTimer); fallbackTimer = setTimeout(finish, text.length * 70); }
}
function stopClip() { const c = clip; clip = null; if (c) { c.onended = null; try { c.stop(); } catch (e) {} } }
function stopSpeech() { stopClip(); stopCallout(); stopComm(); if ("speechSynthesis" in window) speechSynthesis.cancel(); clearTimeout(fallbackTimer); duckTo(1); }

/* ---------------- callouts ---------------- */
// Short clips in the commentary voice (htg/speech/callouts.py), strung together per event: "Okafor... shot... saved!", "Throw-in,
// Northport", "Foul... yellow card, Silva", and the passer's name in the final third (at most one name every 3 s of match time).
// One at a time and at least 2 s apart; a higher priority cuts a lower one off. Narration, recaps and the tour come first: a callout
// is skipped while a sentence plays, and a sentence waits for the callout under way to finish. Commentary language; on in Casual and Audio only.
const CALL_PRI = { goal: 9, shot: 8, save: 7, card: 6, foul: 5, corner: 4, free_kick: 3, throw_in: 2, goal_kick: 1, out: 1, name: 0 };
const CALL_GAP_S = 2, NAME_EVERY_S = 3, SHOT_END = { saved: "saved", blocked: "blocked", off_target: "wide" };
const callouts = { clips: null, bufs: {}, cur: null, lastA: -99, nameT: -99, held: 0 };  // held: sentences waiting for a callout
if (location.protocol.startsWith("http")) {
  fetch("callouts/callouts.json").then(r => r.ok ? r.json() : null).then(j => { callouts.clips = j && j.clips; preloadCallouts(); }).catch(() => {});
}
function calloutBuf(l, tone, key) {
  const f = callouts.clips && callouts.clips[l] && callouts.clips[l][tone] && callouts.clips[l][tone][key];
  if (!f || !ctx) return null;
  if (!(f in callouts.bufs)) {
    callouts.bufs[f] = fetch("callouts/" + f).then(r => r.ok ? r.arrayBuffer() : null).then(b => b ? ctx.decodeAudioData(b) : null)
      .then(b => b && trimmed(b)).catch(() => null);
  }
  return callouts.bufs[f];
}
// The voice pads each clip with silence; strung together that drags ("Okafor ...... shot"). Keep only the sound: { buf, from, len }.
function trimmed(buf) {
  const d = buf.getChannelData(0), th = 0.01, pad = Math.round(0.03 * buf.sampleRate);
  let i = 0, j = d.length - 1;
  while (i < j && Math.abs(d[i]) < th) i++;
  while (j > i && Math.abs(d[j]) < th) j--;
  i = Math.max(0, i - pad); j = Math.min(d.length - 1, j + pad);
  return { buf, from: i / buf.sampleRate, len: (j - i) / buf.sampleRate };
}
function preloadCallouts() {  // ~75 small clips per language, decoded once, so a callout starts on time
  const c = callouts.clips && callouts.clips[lang()];
  if (c && ctx) Object.keys(c).forEach(tone => Object.keys(c[tone]).forEach(key => calloutBuf(lang(), tone, key)));
}
const inFinalThird = (r, team) => r && r.in_play && r.team === team && (team === "HOME" ? r.x >= 70 : r.x <= 35);  // HOME attacks x = 105
// The words for one event_cue: { pri, tone, keys, name } or null. Keys are clip keys: word ids, club names, player names.
function calloutFor(m) {
  const k = m.kind, who = live.players[m.player_id], side = live.teams[m.team], clubKey = side && side.name_en;
  if (k === "goal") return { pri: CALL_PRI.goal, tone: "excited", keys: ["goal", who] };
  if (k === "shot" && m.outcome !== "goal") return { pri: CALL_PRI.shot, tone: "excited", keys: [who, "shot", SHOT_END[m.outcome]], name: true };
  if (k === "foul" && m.card) return { pri: CALL_PRI.card, tone: "excited", keys: ["foul", m.card + "_card", who] };
  if (k === "foul") return { pri: CALL_PRI.foul, tone: "normal", keys: ["foul"] };
  if (k === "restart" && m.restart in CALL_PRI) return { pri: CALL_PRI[m.restart], tone: "normal", keys: [m.restart, clubKey] };
  if (k === "out") return { pri: CALL_PRI.out, tone: "normal", keys: ["out"] };
  if (k === "pass" && who && m.t - callouts.nameT >= NAME_EVERY_S && inFinalThird(live.cur, m.team)) return { pri: CALL_PRI.name, tone: "normal", keys: [who], name: true };
  return null;
}
function callout(m, a) {
  if (!$("L_callout").checked || !callouts.clips || !live.teams || tour.on || clip || comm || callouts.held || ("speechSynthesis" in window && speechSynthesis.speaking)) return;
  const c = calloutFor(m), cur = callouts.cur;
  if (!c) return;
  const busy = (cur && a < cur.end) || a - callouts.lastA < CALL_GAP_S;
  if (busy && !(cur && c.pri > cur.pri)) return;
  const bufs = c.keys.filter(Boolean).map(key => calloutBuf(lang(), c.tone, key));
  if (!bufs.length || bufs.some(b => !b)) return;  // a missing clip: say nothing rather than half a callout
  stopCallout();
  const entry = callouts.cur = { pri: c.pri, end: a + 1.5, srcs: [] }, gen = live.gen;  // end is a guess until the clips are decoded
  callouts.lastA = a;
  if (c.name) callouts.nameT = m.t;
  Promise.all(bufs).then(bs => {
    if (callouts.cur !== entry || live.gen !== gen || !live.ws || bs.some(b => !b)) return;
    let x = Math.max(a, ctx.currentTime);
    duck.gain.setTargetAtTime(0.5, x, 0.05);
    bs.forEach((b, i) => {
      const s = ctx.createBufferSource(); s.buffer = b.buf; s.connect(voiceBus); s.start(x, b.from, b.len); entry.srcs.push(s);
      x += b.len + (i === 0 && c.name ? 0.25 : 0.08);  // "Okafor... shot!": a beat after the name
    });
    entry.end = x;
    duck.gain.setTargetAtTime(1, x, 0.15);
  });
}
function stopCallout() {
  const c = callouts.cur; callouts.cur = null;
  if (!c || !ctx) return;
  c.srcs.forEach(s => { try { s.stop(); } catch (e) {} });
  duck.gain.cancelScheduledValues(ctx.currentTime); duck.gain.setTargetAtTime(1, ctx.currentTime, 0.08);
}

/* ---------------- live commentator ---------------- */
// Lines from the server's live commentator (Foundry, verified, commentary voice), played when the play clock reaches their match time.
// One voice at a time, by priority: a goal line cuts anything; otherwise recaps, narration and the tour come first, and a line whose
// slot is taken waits up to COMM_WAIT_S, then is dropped as stale. Callouts yield: one under way finishes, no new one starts meanwhile.
const COMM_WAIT_S = 3;
let comm = null, clipGoal = false;  // the commentator line playing: { src, goal }; whether the narration clip playing is a goal
function commentaryLine(m, a) {
  const l = lang();
  if (!m.text[l]) return;  // the Verifier passed only the other language
  const buf = decodeClip(m, l), gen = live.gen, until = a + (m.goal ? 2 * COMM_WAIT_S : COMM_WAIT_S);
  let holding = false;
  const release = () => { if (holding) { holding = false; callouts.held = Math.max(0, callouts.held - 1); } };
  const tryPlay = async () => {
    if (live.gen !== gen || !live.ws) { release(); return; }
    const voice = tour.on || clip || comm || ("speechSynthesis" in window && speechSynthesis.speaking);
    const calling = callouts.cur && callouts.cur.end > ctx.currentTime;
    // A goal line cuts anything except a goal sentence already under way (same goal, said once): then it waits like the others.
    if ((!m.goal && (voice || calling)) || (m.goal && clip && clipGoal)) {
      if (calling && !holding) { holding = true; callouts.held++; }
      if (ctx.currentTime < until) setTimeout(tryPlay, 150); else release();
      return;
    }
    release();
    const b = await buf;
    if (live.gen !== gen || !live.ws) return;
    if (m.goal) { stopClip(); stopComm(); if ("speechSynthesis" in window) speechSynthesis.cancel(); }
    stopCallout();
    setCaption(m.text, true); addFeed(m);
    $("captionTag").textContent = commTag(m);
    $("captionMine").hidden = true;
    const idle = () => setTimeout(() => { if (!comm && !clip) $("captionTag").classList.add("idle"); }, 400);
    if (!$("L_voice").checked || !b) { idle(); return; }
    duckTo(0.3);
    const src = ctx.createBufferSource(); src.buffer = b; src.connect(voiceBus);
    comm = { src, goal: !!m.goal };
    src.onended = () => { if (comm && comm.src === src) { comm = null; duckTo(1); idle(); } };
    src.start();
  };
  setTimeout(tryPlay, Math.max(0, (a - ctx.currentTime) * 1000));
}
function stopComm() { const c = comm; comm = null; if (c) { c.src.onended = null; try { c.src.stop(); } catch (e) {} } }
const commTag = m => m.source === "live" ? `${t("liveTag")} · ${(m.latency_s ?? 0).toFixed(1).replace(".", uiLang === "tr" ? "," : ".")} ${t("secs")}` : t("fallbackTag");
// The feed: the match's last FEED_N lines as they were spoken (never before), newest on top, by the caption's dual-language rules;
// the list scrolls (mouse, touch, or arrow keys once focused). Not a live region: the caption already speaks.
const FEED_N = 60;
function addFeed(m) { live.feed.unshift(m); live.feed.length = Math.min(live.feed.length, FEED_N); renderFeed(); }
function renderFeed() {
  // A listener scrolled down to older lines keeps their place when a new line arrives on top; at the top, the new line shows.
  const ol = $("feedList"), keep = ol.scrollTop > 0 ? ol.scrollHeight - ol.scrollTop : null;
  ol.replaceChildren();
  if (!live.feed.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = t("feedEmpty"); ol.append(li); return; }
  for (const m of live.feed) {
    const li = document.createElement("li"), tm = document.createElement("time"), tag = document.createElement("span"), p = document.createElement("span");
    const main = m.text[lang()] !== undefined ? lang() : uiLang, sub = main !== uiLang ? m.text[uiLang] : undefined;
    tm.textContent = `${Math.floor(m.t / 60) + 1}'`; tag.className = "tag" + (m.source === "live" ? "" : " dim"); tag.textContent = commTag(m);
    p.textContent = m.text[main] ?? ""; p.lang = main;
    if (sub) { const sm = document.createElement("small"); sm.lang = uiLang; sm.textContent = sub; p.append(sm); }
    li.append(tm, tag, p); ol.append(li);
  }
  if (keep !== null) ol.scrollTop = ol.scrollHeight - keep;
}

