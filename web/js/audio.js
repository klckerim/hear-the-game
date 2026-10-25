// Audio: Web Audio graph and the sound of the match.
/* ---------------- audio ---------------- */
let ctx, master, duck, voiceBus, noiseBuf, waves, session = null, clip = null;
const layerOn = () => ({ ball: $("L_ball").checked, press: $("L_press").checked, crowd: $("L_crowd").checked,
  cue: $("L_cue").checked, voice: $("L_voice").checked });

function initAudio() {
  if (ctx) return;
  // iOS treats Web Audio as ambient sound and mutes it with the silent switch; "playback" makes it play like a music app (Safari 17+).
  try { if (navigator.audioSession) navigator.audioSession.type = "playback"; } catch (e) {}
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  const comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -14; comp.ratio.value = 4;
  master = ctx.createGain(); master.gain.value = 0.9;
  duck = ctx.createGain();
  voiceBus = ctx.createGain();  // narration clips bypass the duck gain, so only the sound under the voice gets quieter
  duck.connect(master); voiceBus.connect(master); master.connect(comp); comp.connect(ctx.destination);
  noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const nd = noiseBuf.getChannelData(0);
  for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
  const mk = imag => ctx.createPeriodicWave(new Float32Array(imag.length), new Float32Array(imag));
  waves = { HOME: mk([0, 1, 0.35]), AWAY: mk([0, 1, 0, 0.4, 0, 0.22]) };
}

function out(dest, pan) {
  const p = ctx.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan || 0));
  p.connect(dest); return p;
}
function envGain(dest, at, peak, attack, len) {
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), at + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, at + len);
  g.connect(dest); return g;
}
function sndTick(dest, at, team, danger, pan, vol) {
  const o = ctx.createOscillator();
  o.setPeriodicWave(waves[team]);
  o.frequency.value = PENTA[Math.min(PENTA.length - 1, Math.round(danger * (PENTA.length - 1)))];
  o.connect(envGain(out(dest, pan), at, vol, 0.005, 0.12));
  o.start(at); o.stop(at + 0.13);
}
function sndBeat(dest, at, vol) {
  const o = ctx.createOscillator();
  o.frequency.setValueAtTime(75, at); o.frequency.linearRampToValueAtTime(50, at + 0.18);
  o.connect(envGain(dest, at, vol, 0.004, 0.2));
  o.start(at); o.stop(at + 0.21);
}
function sndNoise(dest, at, dur, type, freq, q, vol, pan, attack) {
  const s = ctx.createBufferSource(); s.buffer = noiseBuf;
  const f = ctx.createBiquadFilter(); f.type = type; f.frequency.setValueAtTime(freq, at); f.Q.value = q;
  s.connect(f); f.connect(envGain(out(dest, pan), at, vol, attack, dur));
  s.start(at, Math.random()); s.stop(at + dur + 0.02);
  return f;
}
const sndClick = (d, at, pan) => sndNoise(d, at, 0.03, "bandpass", 2600, 1.2, 0.5, pan, 0.001);
function sndWhoosh(d, at, pan) {
  const f = sndNoise(d, at, 0.4, "highpass", 600, 0.7, 0.55, pan, 0.25);
  f.frequency.exponentialRampToValueAtTime(3500, at + 0.35);
}
function sndThud(d, at, pan) {
  const o = ctx.createOscillator(); o.frequency.value = 85;
  o.connect(envGain(out(d, pan), at, 0.8, 0.002, 0.28)); o.start(at); o.stop(at + 0.3);
  sndNoise(d, at, 0.18, "lowpass", 400, 0.7, 0.35, pan, 0.002);
}
function sndWhistle(d, at, len, vol) {
  const o = ctx.createOscillator(), lfo = ctx.createOscillator(), lg = ctx.createGain();
  o.frequency.value = 2900; lfo.frequency.value = 28; lg.gain.value = 120;
  lfo.connect(lg); lg.connect(o.frequency);
  const g = ctx.createGain(); g.gain.setValueAtTime(0.0001, at);
  g.gain.linearRampToValueAtTime(vol, at + 0.02); g.gain.setValueAtTime(vol, at + len - 0.05);
  g.gain.linearRampToValueAtTime(0.0001, at + len); g.connect(d);
  o.connect(g); o.start(at); lfo.start(at); o.stop(at + len); lfo.stop(at + len);
}
function sndEarcon(d, at, pan) {
  [[1318.5, 0, 0.16], [1975.5, 0.14, 0.45]].forEach(([fr, off, len]) => {
    const o = ctx.createOscillator(); o.frequency.value = fr;
    o.connect(envGain(out(d, pan), at + off, 0.18, 0.003, len)); o.start(at + off); o.stop(at + off + len + 0.01);
  });
}
// feel: "for" = your club scored (brighter, longer crowd swell), "against" = short muted crowd and no fanfare, "neutral" = no favourite
const GOAL_CROWD = { neutral: [1800, 0.32, 3.5], for: [3200, 0.45, 6.0], against: [600, 0.12, 1.2] };
function sndGoal(d, at, team, feel = "neutral") {
  const [cutoff, peak, len] = GOAL_CROWD[feel];
  const s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
  const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = cutoff;
  const g = ctx.createGain(); g.gain.setValueAtTime(0, at);
  g.gain.linearRampToValueAtTime(peak, at + 0.6); g.gain.linearRampToValueAtTime(0.0001, at + len);
  s.connect(f); f.connect(g); g.connect(d); s.start(at); s.stop(at + len + 0.1);
  if (feel !== "against") [0, 4, 7, 12].forEach((st, k) => sndTick(d, at + k * 0.13, team, 0.5, 0, 0.3 * (1 + st / 24)));
  sndWhistle(d, at + 0.6, 0.7, 0.05);
}

function newSession() {
  const bus = ctx.createGain(); bus.connect(duck);
  const L = {}; ["ball", "press", "crowd", "cue"].forEach(k => { L[k] = ctx.createGain(); L[k].connect(bus); });
  const crowdSrc = ctx.createBufferSource(); crowdSrc.buffer = noiseBuf; crowdSrc.loop = true;
  const cf = ctx.createBiquadFilter(); cf.type = "lowpass"; cf.frequency.value = 900;
  const cg = ctx.createGain(); cg.gain.value = 0.03;
  crowdSrc.connect(cf); cf.connect(cg); cg.connect(L.crowd); crowdSrc.start();
  return { bus, L, crowdSrc, crowdGain: cg };
}
function endSession(s) {
  if (!s) return;
  s.bus.gain.setTargetAtTime(0, ctx.currentTime, 0.015);
  setTimeout(() => { try { s.crowdSrc.stop(); } catch (e) {} s.bus.disconnect(); }, 250);
}
function applyLayers() {
  if (!session) return;
  const on = layerOn();
  Object.keys(session.L).forEach(k => session.L[k].gain.setTargetAtTime(on[k] ? 1 : 0, ctx.currentTime, 0.03));
}

