// Analyst stats.
/* ---------------- analyst stats ---------------- */
// The table shows what the server's `stats` message says (recap tool `get_stats`); nothing is counted in the browser.
const STAT_ROWS = ["possession_pct", "shots", "pass_completion_pct", "pressing_pct", "corners", "fouls"];
function renderStats() {
  const body = $("statsBody"), st = live.stats && live.stats[live.statsWin];
  $("stHome").textContent = uiTeam("HOME"); $("stAway").textContent = uiTeam("AWAY");
  document.querySelectorAll("#statsWin button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.win === live.statsWin)));
  body.replaceChildren();
  if (!st) { const tr = body.insertRow(), td = tr.insertCell(); td.colSpan = 3; td.className = "note"; td.textContent = t("statsWait"); return; }
  for (const key of STAT_ROWS) {
    const tr = body.insertRow(), th = document.createElement("th"), h = st.home[key], a = st.away[key], pctRow = key.endsWith("_pct");
    th.scope = "row"; th.textContent = t("st_" + key); tr.append(th);
    for (const [side, v] of [["HOME", h], ["AWAY", a]]) {
      const td = tr.insertCell(), val = document.createElement("span"), bar = document.createElement("span"), fill = document.createElement("i");
      val.className = "v"; bar.className = "b"; bar.setAttribute("aria-hidden", "true");
      val.textContent = v === null ? "–" : pctRow ? v + "%" : key === "shots" ? `${v} (${st[side.toLowerCase()].shots_on_target})` : String(v);
      fill.style.width = (v === null ? 0 : pctRow ? v : 100 * v / Math.max(h, a, 1)) + "%"; fill.style.background = teamColor(side);
      bar.append(fill); td.append(val, bar);
    }
  }
}

