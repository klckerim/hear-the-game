// Drawing: the pitch canvas.
/* ---------------- drawing ---------------- */
const pc = $("pitch");
function fit(c) {
  const r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  if (c.width !== Math.round(r.width * dpr) || c.height !== Math.round(r.height * dpr)) { c.width = Math.round(r.width * dpr); c.height = Math.round(r.height * dpr); }
  return { w: c.width, h: c.height, dpr };
}
function teamColor(side) { const i = teamInfo(side); return i ? COLOR[i.color] || "#ccc" : "#ccc"; }
// The pitch in metres (105 x 68, standard markings) with PITCH_M of grass around it, so the touchlines and goal lines meet in
// clean corners and the goals sit behind the goal line. Ball, trail and evidence use the same sx / sy.
const PITCH_M = 2.5;
function drawPitch() {
  const { w, h, dpr } = fit(pc), g = pc.getContext("2d");
  const k = w / (105 + 2 * PITCH_M), sx = x => (x + PITCH_M) * k, sy = y => h - (y + PITCH_M) * k;
  const line = (x0, y0, x1, y1) => { g.beginPath(); g.moveTo(sx(x0), sy(y0)); g.lineTo(sx(x1), sy(y1)); g.stroke(); };
  const rect = (x0, y0, x1, y1) => g.strokeRect(sx(x0), sy(y1), sx(x1) - sx(x0), sy(y0) - sy(y1));
  const arc = (x, y, r, a0, a1) => { g.beginPath(); g.arc(sx(x), sy(y), r * k, a0, a1); g.stroke(); };
  const spot = (x, y) => { g.beginPath(); g.arc(sx(x), sy(y), Math.max(1.5 * dpr, 0.22 * k), 0, Math.PI * 2); g.fill(); };
  g.fillStyle = "#102a1b"; g.fillRect(0, 0, w, h);  // the grass around the pitch, a shade darker
  for (let i = 0; i < 12; i++) { g.fillStyle = i % 2 ? "#12301f" : "#143521"; g.fillRect(sx(i * 8.75), sy(68), 8.75 * k + 0.5, 68 * k); }  // mowing stripes
  g.strokeStyle = g.fillStyle = "rgba(232,239,233,0.38)"; g.lineWidth = 1.5 * dpr; g.lineJoin = "miter";
  rect(0, 0, 105, 68);
  line(52.5, 0, 52.5, 68);
  arc(52.5, 34, 9.15, 0, Math.PI * 2); spot(52.5, 34);
  const D = Math.acos(5.5 / 9.15);  // where the penalty arc leaves the box: 16.5 m line, spot at 11 m
  for (const [gx, d] of [[0, 1], [105, -1]]) {
    rect(Math.min(gx, gx + d * 16.5), 13.84, Math.max(gx, gx + d * 16.5), 54.16);
    rect(Math.min(gx, gx + d * 5.5), 24.84, Math.max(gx, gx + d * 5.5), 43.16);
    spot(gx + d * 11, 34);
    // canvas angles grow clockwise and sy flips y, so the arc outside the box is around angle 0 (right) or PI (left)
    if (d === 1) arc(11, 34, 9.15, -D, D); else arc(94, 34, 9.15, Math.PI - D, Math.PI + D);
    rect(Math.min(gx, gx - d * 2), 30.34, Math.max(gx, gx - d * 2), 37.66);  // the goal, 7.32 m wide and 2 m deep
  }
  [[0, 0, -Math.PI / 2, 0], [105, 0, Math.PI, 3 * Math.PI / 2], [0, 68, 0, Math.PI / 2], [105, 68, Math.PI / 2, Math.PI]]
    .forEach(([x, y, a0, a1]) => arc(x, y, 1, a0, a1));  // corner arcs, 1 m
  drawEvidence(g, sx, sy, dpr);
  const trail = live.trail || [];
  trail.slice(0, -1).forEach((p, i) => {
    if (!p.in_play) return;
    g.fillStyle = teamColor(p.team); g.globalAlpha = 0.5 * (i + 1) / trail.length;
    g.beginPath(); g.arc(sx(p.x), sy(p.y), 4 * dpr, 0, Math.PI * 2); g.fill();
  });
  g.globalAlpha = 1;
  drawCut(g, w, h, dpr);
  const p = live.cur;
  if (!p) return;
  const white = live.teams && live.teams[p.team].color === "white";  // a white ring on a white ball would hide the team: dark ball
  g.beginPath(); g.arc(sx(p.x), sy(p.y), 9 * dpr, 0, Math.PI * 2);
  g.fillStyle = white ? (p.in_play ? "#1d2b26" : "rgba(29,43,38,0.5)") : p.in_play ? "#f5f7f5" : "rgba(245,247,245,0.4)"; g.fill();
  g.lineWidth = 3 * dpr; g.strokeStyle = teamColor(p.team); g.stroke();
}
function drawCut(g, w, h, dpr) {  // the next highlight's minute, large on the pitch for 1.6 s
  const c = live.cutShow; if (!c) return;
  const age = (performance.now() - c.at) / 1000;
  if (age > 1.6) { live.cutShow = null; return; }
  g.globalAlpha = Math.min(1, (1.6 - age) / 0.4);
  g.fillStyle = "rgba(5,8,7,0.55)"; g.fillRect(0, 0, w, h);
  g.fillStyle = "#e8efe9"; g.font = `700 ${Math.round(h * 0.28)}px "Barlow Condensed", "Arial Narrow", sans-serif`;
  g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(c.text, w / 2, h / 2);
  g.globalAlpha = 1; g.textAlign = "start"; g.textBaseline = "alphabetic";
}
function drawPanel() {
  const r = live.cur; if (!r) return;
  $("mDanger").style.width = (r.danger * 100) + "%"; $("vDanger").textContent = r.danger.toFixed(2);
  $("mPress").style.width = (r.pressure * 100) + "%"; $("vPress").textContent = r.pressure.toFixed(2);
  $("mPan").style.left = `calc(${(r.pan + 1) * 50}% - 7px)`;
  $("vPan").textContent = !r.in_play ? "—" : r.pan < -0.33 ? t("left") : r.pan > 0.33 ? t("right") : t("mid");
  $("clock").textContent = live.ended ? `90:00 · ${t("ftShort")}` : clock(r.t);  // the last ball frame is 89:59.9
}
function loop() { drawPitch(); drawPanel(); drawTimeline(); requestAnimationFrame(loop); }

