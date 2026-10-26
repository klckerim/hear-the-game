// Sound tour.
/* ---------------- sound tour ---------------- */
// Before the first start: each step shows a caption, plays its pre-generated voice line (device voice if the clip is missing), then
// the real sound through the same functions the match uses. Text table: web/tour.json. Never starts the match; Skip stops at once.
const tour = { on: false, steps: null, bus: null, src: null, timers: [], clips: {}, wake: null };
const TOUR_DONE = "htg.tour";
const tourWait = s => new Promise(r => { tour.wake = r; tour.timers.push(setTimeout(r, s * 1000)); });
function tourBed(d, a, len, danger) {  // ticks + crowd, as under a live match
  for (let x = 0; x < len; x += 0.2) sndTick(d, a + x, "HOME", danger, 0, 0.14);
  const s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
  const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 900;
  const g = ctx.createGain(); g.gain.setValueAtTime(0.06, a); g.gain.linearRampToValueAtTime(0.0001, a + len);
  s.connect(f); f.connect(g); g.connect(d); s.start(a); s.stop(a + len + 0.05);
}
// Each demo schedules its sound from audio time `a` and returns its length in seconds.
const TOUR_DEMO = {
  ball: (d, a) => { for (let i = 0; i < 10; i++) sndTick(d, a + i * 0.2, "HOME", i / 9, 0, 0.2); return 2.1; },
  wing: (d, a) => { for (let i = 0; i < 10; i++) sndTick(d, a + i * 0.2, "HOME", 0.4, -1 + 2 * i / 9, 0.2); return 2.1; },
  teams: (d, a) => {
    for (let i = 0; i < 5; i++) { sndTick(d, a + i * 0.2, "HOME", 0.4, 0, 0.22); sndTick(d, a + 1.4 + i * 0.2, "AWAY", 0.4, 0, 0.22); }
    return 2.5;
  },
  pressure: (d, a) => { let x = a; for (let i = 0; i < 8; i++) { const p = i / 7; sndBeat(d, x, 0.35 + 0.5 * p); x += 1 / (0.9 + 2.3 * p); } return x - a + 0.2; },
  crowd: (d, a) => {
    const s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
    const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 900;
    const g = ctx.createGain(); g.gain.setValueAtTime(0.03, a); g.gain.linearRampToValueAtTime(0.16, a + 2.2); g.gain.linearRampToValueAtTime(0.0001, a + 2.8);
    s.connect(f); f.connect(g); g.connect(d); s.start(a); s.stop(a + 2.9);
    for (let i = 0; i < 11; i++) sndTick(d, a + i * 0.2, "HOME", i / 10, 0, 0.14);
    return 2.9;
  },
  events: (d, a) => { sndClick(d, a, -0.3); sndWhoosh(d, a + 0.6, 0.3); sndThud(d, a + 1.3, 0.3); sndWhistle(d, a + 2.0, 0.4, 0.05); return 2.6; },
  goal: (d, a) => { sndGoal(d, a, "HOME", "for"); sndGoal(d, a + 3.6, "AWAY", "against"); return 5.0; },
  favourite: (d, a) => { sndEarcon(d, a, -0.5); sndEarcon(d, a + 0.8, 0.5); return 1.6; },
};
async function loadTour() {
  if (!location.protocol.startsWith("http")) return null;  // opened as a file (run_local): no tour
  try { const r = await fetch("tour/tour.json"); return r.ok ? (await r.json()).steps : null; } catch (e) { return null; }
}
async function tourClip(step, l) {
  const key = step.id + "_" + l;
  if (!(key in tour.clips)) {
    tour.clips[key] = fetch(`tour/${key}.mp3`).then(r => r.ok ? r.arrayBuffer() : null).then(b => b ? ctx.decodeAudioData(b) : null).catch(() => null);
  }
  return tour.clips[key];
}
function tourVoice(step) {
  const l = lang(), text = step[l];
  setCaption(step, true, () => t("tourTag")); $("captionMine").hidden = true;
  return new Promise(async done => {
    tour.wake = done;
    const buf = await tourClip(step, l);
    if (!tour.on) return done();
    if (buf) {
      const src = tour.src = ctx.createBufferSource(); src.buffer = buf; src.connect(voiceBus); src.onended = done; src.start();
      return;
    }
    const v = voiceFor[l];
    if ("speechSynthesis" in window && v) {
      const u = new SpeechSynthesisUtterance(text); u.voice = v; u.lang = v.lang; u.onend = done; u.onerror = done;
      speechSynthesis.cancel(); speechSynthesis.speak(u);
    } else tour.timers.push(setTimeout(done, text.length * 60));
  });
}
async function runTour() {
  initAudio(); ctx.resume(); primeVoice();
  tour.on = true; tour.bus = ctx.createGain(); tour.bus.connect(duck); syncLiveRegions();
  renderTourBtn();
  for (const l of ["en", "tr"]) tour.steps.forEach(s => tourClip(s, l));  // fetch and decode ahead, so steps follow without gaps
  for (const step of tour.steps) {
    if (!tour.on) return;
    if (step.demo === "duck") {  // the voice line itself shows the ducking: the match bed dips under it
      tourBed(tour.bus, ctx.currentTime + 0.05, 6, 0.35);
      await tourWait(1.0); if (!tour.on) return;
      duckTo(0.3); await tourVoice(step); duckTo(1);
      await tourWait(0.6);
      continue;
    }
    await tourVoice(step);
    if (!tour.on) return;
    const demo = TOUR_DEMO[step.demo];
    await tourWait(demo ? demo(tour.bus, ctx.currentTime + 0.1) + 0.4 : 0.2);
  }
  endTour();
}
function endTour() {
  if (!tour.on) return;
  tour.on = false; store.set(TOUR_DONE, "1"); syncLiveRegions();
  tour.timers.forEach(clearTimeout); tour.timers = [];
  const src = tour.src; tour.src = null; if (src) { src.onended = null; try { src.stop(); } catch (e) {} }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (tour.bus) { const b = tour.bus; tour.bus = null; b.gain.setTargetAtTime(0, ctx.currentTime, 0.01); setTimeout(() => b.disconnect(), 200); }
  duckTo(1);
  if (tour.wake) { const w = tour.wake; tour.wake = null; w(); }  // lets the running step return at once
  idleCaption();
  renderTourBtn();
}
// The tour offer is a first-visit banner: shown until the tour is done, skipped or dismissed (same localStorage key), then gone.
function renderTourBtn() {
  const b = $("tourBtn");
  $("tourBanner").hidden = !tour.steps || (!tour.on && store.get(TOUR_DONE) === "1");
  b.textContent = tour.on ? t("tourSkip") : t("tourStart");
  b.setAttribute("aria-pressed", String(tour.on));
}

