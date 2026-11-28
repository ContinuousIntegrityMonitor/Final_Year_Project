"""Render the live status board. The first paint is HTML; the page then polls."""

from __future__ import annotations

import html

from cim.dashboard.board import Board
from cim.mcp.envelope import WARMUP, ToolEnvelope

_CSS = """
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");
:root {
  color-scheme: dark;
  --bg: #12151a;
  --bg-2: #171b22;
  --surface: #1c222c;
  --surface-2: #232a36;
  --ink: #e8eaed;
  --muted: #9aa3ad;
  --line: rgba(232, 234, 237, 0.12);
  --accent: #6b8cae;
  --accent-ink: #12151a;
  --safe: #3d9a6a;
  --warn: #c45c26;
  --danger: #c62828;
  --ridge: #c5ccd6;
  --pad: #151a21;
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #eef1f4;
  --bg-2: #e4e8ee;
  --surface: #ffffff;
  --surface-2: #f7f8fa;
  --ink: #1a2330;
  --muted: #5b6775;
  --line: rgba(26, 35, 48, 0.12);
  --accent: #3d5f80;
  --accent-ink: #ffffff;
  --safe: #1f7a4d;
  --warn: #a84a1a;
  --danger: #b71c1c;
  --ridge: #3a4654;
  --pad: #e8ecf1;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  font: 15px/1.45 "IBM Plex Sans", "Segoe UI", sans-serif;
  font-variant-numeric: tabular-nums;
  background:
    radial-gradient(ellipse 80% 50% at 10% -10%, rgba(107, 140, 174, 0.18), transparent 55%),
    radial-gradient(ellipse 60% 40% at 100% 0%, rgba(61, 154, 106, 0.08), transparent 50%),
    linear-gradient(180deg, var(--bg-2), var(--bg) 40%);
}
button {
  font: inherit;
  font-weight: 600;
  color: var(--ink);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.55rem 1rem;
  cursor: pointer;
}
button.primary {
  background: var(--accent);
  color: var(--accent-ink);
  border-color: transparent;
}
button:disabled { opacity: 0.4; cursor: not-allowed; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.shell {
  max-width: 72rem;
  margin: 0 auto;
  padding: 1.1rem 1.25rem 5.5rem;
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding-bottom: 0.9rem;
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: baseline; gap: 0.55rem; }
.word {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}
h1 {
  margin: 0;
  font-size: 1.55rem;
  font-weight: 650;
  letter-spacing: -0.03em;
}
.actions { display: flex; align-items: center; gap: 0.7rem; }
.live {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  color: var(--muted);
  font-size: 0.92rem;
}
.dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--safe);
}
@media (prefers-reduced-motion: no-preference) {
  .dot { animation: pulse 2.2s ease-in-out infinite; }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
#theme {
  background: transparent;
  border-color: var(--line);
  color: var(--ink);
  font-weight: 500;
  padding: 0.35rem 0.75rem;
  font-size: 0.85rem;
}
.board {
  display: grid;
  grid-template-columns: minmax(14rem, 17rem) minmax(14rem, 1fr) minmax(16rem, 22rem);
  gap: 1.1rem;
  margin-top: 1.15rem;
  align-items: start;
}
.verdict, .rail, #home {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 0.85rem;
  padding: 1rem 1.05rem 1.1rem;
}
.verdict .banner {
  margin: 0.55rem 0 0;
  font-size: 1.2rem;
  line-height: 1.3;
  font-weight: 600;
}
.connection { margin: 0; font-weight: 600; font-size: 0.95rem; }
.connection.on { color: var(--safe); }
.connection.off { color: var(--muted); }
.ok { color: var(--safe); }
.bad { color: var(--danger); }
.check { margin: 0.45rem 0 0; color: var(--muted); font-size: 0.88rem; }
.warning {
  margin-top: 0.85rem;
  padding: 0.75rem 0.8rem;
  border: 1px solid var(--danger);
  border-radius: 0.65rem;
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}
.warning strong { color: var(--danger); }
.warning p { margin: 0.35rem 0 0; font-size: 0.9rem; }
.alert-line { margin: 0.85rem 0 0; color: var(--muted); font-size: 0.9rem; }
.rail h2, #home h2, #mcp-schema h2, #exchange h2, .panel-title {
  margin: 0 0 0.55rem;
  font-size: 0.95rem;
  font-weight: 650;
}
.side-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.85rem;
  margin-top: 1rem;
}
@media (max-width: 960px) {
  .side-panels { grid-template-columns: 1fr; }
}
.panel-block {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 0.85rem;
  padding: 1rem 1.05rem;
}
.panel-block h2 {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}
.panel-block h2 .tag {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.pill {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.12rem 0.4rem;
  border-radius: 0.35rem;
  border: 1px solid var(--line);
}
.pill.healthy {
  color: var(--safe);
  border-color: color-mix(in srgb, var(--safe) 45%, transparent);
}
.pill.learning {
  color: #c9b66a;
  border-color: color-mix(in srgb, #c9b66a 45%, transparent);
}
.pill.warning {
  color: var(--warn);
  border-color: color-mix(in srgb, var(--warn) 45%, transparent);
}
.skill-line {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.45rem 0;
  border-top: 1px solid var(--line);
  font-size: 0.86rem;
}
.skill-line:first-of-type { border-top: 0; padding-top: 0; }
.skill-line .meta { color: var(--muted); font-size: 0.78rem; margin-top: 0.15rem; }
.bar {
  height: 4px;
  background: var(--pad);
  border-radius: 2px;
  margin-top: 0.3rem;
  overflow: hidden;
}
.bar > i {
  display: block;
  height: 100%;
  background: #c9b66a;
  border-radius: 2px;
}
.bar.ready > i { background: var(--safe); }
.print-pad {
  width: 100%;
  aspect-ratio: 1 / 1.15;
  border-radius: 0.55rem;
  background: var(--pad);
  border: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: center;
}
.print { width: 88%; height: auto; display: block; }
.ridge {
  fill: none;
  stroke: var(--ridge);
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 800;
  stroke-dashoffset: 800;
  animation: draw 0.7s ease forwards;
}
.ridge.unusual { stroke: var(--danger); stroke-width: 2.6; }
.ridge.broken {
  stroke: var(--danger);
  stroke-width: 2.4;
  stroke-dasharray: 6 7;
  stroke-dashoffset: 0;
  animation: none;
  opacity: 0.85;
}
@keyframes draw { to { stroke-dashoffset: 0; } }
.legend {
  margin: 0.65rem 0 0;
  color: var(--muted);
  font-size: 0.85rem;
  text-align: center;
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.55rem;
}
.stat {
  padding: 0.45rem 0.35rem;
  border-radius: 0.5rem;
  background: var(--surface-2);
  text-align: center;
}
.stat b { display: block; font-size: 1.35rem; line-height: 1.1; font-weight: 650; }
.stat span { color: var(--muted); font-size: 0.75rem; }
details { margin-top: 0.85rem; }
summary {
  cursor: pointer;
  font-weight: 650;
  color: var(--accent);
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
#home section { margin-top: 0.95rem; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}
th, td {
  text-align: left;
  padding: 0.4rem 0.35rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th { color: var(--muted); font-weight: 600; font-size: 0.78rem; }
code, pre {
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: 0.82rem;
}
.note, .empty { color: var(--muted); margin: 0.35rem 0 0; font-size: 0.88rem; }
.demo-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  padding: 0.75rem 1rem calc(0.75rem + env(safe-area-inset-bottom));
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  border-top: 1px solid var(--line);
  backdrop-filter: blur(10px);
}
#mcp-schema, #exchange {
  margin-top: 1rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 0.85rem;
  padding: 1rem 1.05rem;
}
#exchange h3 { margin: 0.75rem 0 0.3rem; font-size: 0.9rem; }
pre {
  margin: 0;
  padding: 0.7rem 0.75rem;
  background: var(--pad);
  border-radius: 0.5rem;
  border: 1px solid var(--line);
  white-space: pre-wrap;
  overflow-x: auto;
}
@media (prefers-reduced-motion: reduce) {
  .ridge { animation: none; stroke-dashoffset: 0; }
  .dot { animation: none; }
}
@media (max-width: 960px) {
  .board { grid-template-columns: 1fr; }
  .shell { padding-bottom: 7rem; }
  .stats { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 640px) {
  .top { flex-direction: column; align-items: flex-start; }
  table, tbody, tr, td { display: block; width: 100%; }
  thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  tr { border-bottom: 1px solid var(--line); padding: 0.35rem 0; }
  td { border: none; padding: 0.1rem 0; }
  td::before {
    content: attr(data-label);
    display: block;
    color: var(--muted);
    font-size: 0.75rem;
  }
}
"""

_SCRIPT = """
<script>
(function () {
  var root = document.documentElement;
  var button = document.getElementById("theme");
  var live = document.getElementById("live-state");
  var region = document.getElementById("live");
  function savedTheme() {
    try { return localStorage.getItem("cim-theme"); } catch (e) { return null; }
  }
  function applyTheme(mode) {
    if (mode === "light") root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    button.textContent = root.getAttribute("data-theme") === "light"
      ? "Steel theme" : "Pearl theme";
  }
  applyTheme(savedTheme());
  button.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "light" ? "steel" : "light";
    try { localStorage.setItem("cim-theme", next === "light" ? "light" : "steel"); } catch (e) {}
    applyTheme(next);
  });
  function node(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }
  function cell(label, text) {
    var td = node("td", "", text);
    td.setAttribute("data-label", label);
    return td;
  }
  function table(headers, rows) {
    var wrap = document.createElement("table");
    var head = document.createElement("thead");
    var hr = document.createElement("tr");
    headers.forEach(function (name) { hr.appendChild(node("th", "", name)); });
    head.appendChild(hr);
    var body = document.createElement("tbody");
    rows.forEach(function (row) { body.appendChild(row); });
    wrap.appendChild(head);
    wrap.appendChild(body);
    return wrap;
  }
  function headline(data) {
    var p = node("p", "banner");
    p.id = "status";
    if (data.empty) {
      p.appendChild(document.createTextNode("Nothing recorded yet. Start one with "));
      p.appendChild(node("code", "", "cim proxy --db store.sqlite -- <server command>"));
      p.appendChild(document.createTextNode(" or load a tool list with "));
      p.appendChild(node("code", "", "cim inventory"));
      p.appendChild(document.createTextNode("."));
      return p;
    }
    var strong = node("strong", data.chain_ok ? "ok" : "bad");
    // Split so empty/broken first-paint tests do not match this script source.
    strong.textContent = data.chain_ok ? "Record is " + "safe" : "Record was " + "changed";
    p.appendChild(strong);
    if (!data.chain_ok) {
      var where = data.broken_at == null ? "unknown" : String(data.broken_at);
      p.appendChild(document.createTextNode(
        ". Entry " + where + " no longer matches. " + data.chain_reason +
        " The list below is still shown. Do not trust it until a good copy passes the check."
      ));
      return p;
    }
    if (data.changes.length) {
      var noun = data.changes.length === 1 ? "change" : "changes";
      p.appendChild(document.createTextNode(
        ". Something new showed up. " + data.changes.length + " " + noun + "."
      ));
      return p;
    }
    p.appendChild(document.createTextNode(
      ". Nothing new since this server was first seen. " + data.record_count + " entries."
    ));
    return p;
  }
  var seen = region.getAttribute("data-sig") || "";
  var drawn = {};
  var lineQueue = [];
  var pumping = false;
  function signature(data) {
    var skillsN = data.skills && data.skills.summary ? data.skills.summary.skills : 0;
    var skillWarn = data.skills && data.skills.summary ? data.skills.summary.warning : 0;
    return data.links.map(function (link) { return link.record_id; }).join(",") +
      "|" + data.chain_ok + "|" + data.broken_at + "|" + data.changes.length +
      "|" + data.connected + "|" + data.alerts.length + "|" + skillsN + "|" + skillWarn;
  }
  function refresh(data) {
    var sig = signature(data);
    if (sig === seen) return;
    seen = sig;
    var conn = document.getElementById("connection");
    if (conn) conn.replaceWith(connectionLine(data));
    var status = document.getElementById("status");
    if (status) status.replaceWith(headline(data));
    var check = document.querySelector(".check");
    if (check) check.replaceWith(selfCheck(data));
    var warnings = document.getElementById("warnings");
    if (warnings) warnings.replaceWith(alertLine(data));
    var home = document.getElementById("home");
    if (!home) return;
    home.replaceChildren();
    home.appendChild(stats(data));
    home.appendChild(detailList(data));
    var panels = document.getElementById("side-panels");
    if (panels) {
      panels.replaceChildren();
      panels.appendChild(mcpPanel(data));
      panels.appendChild(skillsPanel(data));
    }
    showSchema(data);
  }
  function connectionLine(data) {
    var connected = data.connected === true;
    var p = node("p", connected ? "connection on" : "connection off");
    p.id = "connection";
    if (connected) {
      var names = data.tools.slice(0, 3).map(function (tool) { return tool.name; }).join(", ");
      var more = data.tools.length > 3 ? " and " + (data.tools.length - 3) + " more" : "";
      p.textContent = "Connected. " + names + more + ".";
    } else if (data.demo) {
      p.textContent = "Disconnected. Clear and start again to reconnect.";
    } else if (data.tools.length || data.record_count) {
      p.textContent = "Store loaded. No live demo MCP connection (monitoring only).";
    } else {
      p.textContent = "Not connected. Connect an MCP to begin.";
    }
    var use = document.getElementById("call-normal");
    var changed = document.getElementById("call-new");
    var connect = document.getElementById("call-connect");
    var tamper = document.getElementById("call-tamper");
    var clear = document.getElementById("call-clear");
    if (use) use.disabled = !connected;
    if (changed) changed.disabled = !connected;
    if (tamper) tamper.disabled = !connected || data.record_count < 2;
    if (connect) connect.disabled = connected || data.record_count > 0;
    if (clear) clear.disabled = data.record_count < 1 && !data.tools.length;
    if (connect) connect.classList.toggle("primary", !connected && data.record_count < 1);
    if (use) use.classList.toggle("primary", connected);
    if (clear) clear.classList.toggle("primary", !connected && data.record_count > 0);
    return p;
  }
  function stat(value, label) {
    var box = node("div", "stat");
    box.appendChild(node("b", "", String(value)));
    box.appendChild(node("span", "", label));
    return box;
  }
  function stats(data) {
    var wrap = node("div", "stats");
    var skills = (data.skills && data.skills.summary) ? data.skills.summary.skills : 0;
    var skillAlerts = (data.skills && data.skills.summary) ? (data.skills.summary.alerts || 0) : 0;
    wrap.appendChild(stat(data.tools.length, "MCP tools"));
    wrap.appendChild(stat(skills, "Skills"));
    wrap.appendChild(stat(data.changes.length, "MCP changes"));
    wrap.appendChild(stat(data.alerts.length + skillAlerts, "Alerts"));
    return wrap;
  }
  function pill(state) {
    return node("span", "pill " + state, state);
  }
  function mcpPanel(data) {
    var box = node("section", "panel-block");
    box.id = "mcp-panel";
    var h = node("h2", "panel-title", "MCP");
    h.appendChild(node("span", "tag", "servers & tools"));
    box.appendChild(h);
    box.appendChild(node(
      "p",
      "note",
      data.servers.length + " server(s), " + data.tools.length + " tool(s), " +
      data.calls.length + " recent call(s)."
    ));
    if (!data.servers.length && !data.tools.length) {
      box.appendChild(node("p", "empty", "No MCP servers in this store yet."));
      return box;
    }
    data.servers.forEach(function (serverId) {
      var tools = data.tools.filter(function (t) { return t.server_id === serverId; });
      var line = node("div", "skill-line");
      var left = node("div", "");
      left.appendChild(node("div", "", serverId));
      left.appendChild(node(
        "div",
        "meta",
        tools.length ? tools.map(function (t) { return t.name; }).join(", ") : "no tools pinned"
      ));
      line.appendChild(left);
      line.appendChild(pill(tools.length ? "healthy" : "learning"));
      box.appendChild(line);
    });
    return box;
  }
  function skillsPanel(data) {
    var box = node("section", "panel-block");
    box.id = "skills-panel";
    var h = node("h2", "panel-title", "Skills");
    h.appendChild(node("span", "tag", "U1"));
    box.appendChild(h);
    var skills = data.skills;
    if (!skills || !skills.skills || !skills.skills.length) {
      box.appendChild(node("p", "empty", "No skills in this store yet."));
      return box;
    }
    var s = skills.summary;
    box.appendChild(node(
      "p",
      "note",
      s.skills + " installed · " + s.healthy + " healthy · " +
      s.learning + " learning · " + s.warning + " warning"
    ));
    var warmup = skills.warmup || data.warmup || 30;
    skills.skills.forEach(function (row) {
      var line = node("div", "skill-line");
      var left = node("div", "");
      left.appendChild(node("div", "", row.name || row.skill_id));
      var bits = [];
      if (row.integrity && row.integrity.state !== "unchanged") {
        bits.push("files " + row.integrity.state +
          (row.integrity.changed_paths && row.integrity.changed_paths.length
            ? " (" + row.integrity.changed_paths.join(", ") + ")" : ""));
      } else {
        bits.push("files unchanged");
      }
      var obs = row.behaviour && row.behaviour.observations != null
        ? row.behaviour.observations : 0;
      bits.push(obs + " of " + warmup);
      left.appendChild(node("div", "meta", bits.join(" · ")));
      var bar = node("div", "bar" + (row.state === "healthy" ? " ready" : ""));
      var fill = document.createElement("i");
      fill.style.width = Math.min(100, (obs / warmup) * 100) + "%";
      bar.appendChild(fill);
      left.appendChild(bar);
      line.appendChild(left);
      line.appendChild(pill(row.state || "learning"));
      box.appendChild(line);
    });
    return box;
  }
  function alertLine(data) {
    var i;
    if (!data.chain_ok) {
      var where = data.broken_at == null ? "unknown" : String(data.broken_at);
      var box = node("div", "warning");
      box.id = "warnings";
      box.setAttribute("role", "status");
      box.appendChild(node("strong", "", "Warning. "));
      box.appendChild(document.createTextNode("An old log was changed. MCP disconnected."));
      box.appendChild(node(
        "p",
        "",
        "Entry " + where + " no longer matches. Each later entry depends on the " +
        "fingerprint before it, so the rest of the chain cannot be trusted."
      ));
      return box;
    }
    var drift = null;
    for (i = 0; i < data.alerts.length; i++) {
      if (data.alerts[i].code === "mcp_behaviour_drift") {
        drift = data.alerts[i];
        break;
      }
    }
    if (!drift) {
      var quiet = node("p", "alert-line", "No behaviour alert.");
      quiet.id = "warnings";
      return quiet;
    }
    var warn = node("div", "warning");
    warn.id = "warnings";
    warn.setAttribute("role", "status");
    warn.appendChild(node("strong", "", "Warning. "));
    warn.appendChild(document.createTextNode("Strange behaviour detected. MCP disconnected."));
    warn.appendChild(node("p", "", "Input change: " + (drift.input_change || "")));
    warn.appendChild(node("p", "", "Output change: " + (drift.output_change || "")));
    return warn;
  }
  function detailList(data) {
    var box = document.createElement("details");
    box.open = true;
    var summary = document.createElement("summary");
    summary.textContent = "See the list";
    box.appendChild(summary);
    box.appendChild(changes(data));
    box.appendChild(tools(data));
    box.appendChild(calls(data));
    box.appendChild(patterns(data));
    box.appendChild(skillChanges(data));
    return box;
  }
  function skillChanges(data) {
    var section = node("section", "");
    section.appendChild(node("h2", "", "Skill changes"));
    var rows = [];
    if (data.skills && data.skills.changes) {
      rows = data.skills.changes.map(function (change) {
        var tr = document.createElement("tr");
        tr.appendChild(cell("When", change.ts));
        tr.appendChild(cell("Skill", change.skill_id));
        tr.appendChild(cell("Change", change.change));
        tr.appendChild(cell("Path", change.path || ""));
        return tr;
      });
    }
    if (!rows.length) section.appendChild(node("p", "empty", "No skill file changes."));
    else section.appendChild(table(["When", "Skill", "Change", "Path"], rows));
    return section;
  }
  function selfCheck(data) {
    if (data.empty) return node("p", "check", "Waiting for a session.");
    if (!data.chain_ok) {
      var where = data.broken_at == null ? "unknown" : String(data.broken_at);
      return node(
        "p",
        "check bad",
        "Record check failed at entry " + where + ". Later entries no longer match the line."
      );
    }
    return node(
      "p",
      "check ok",
      "Record check passed. " + data.record_count + " entries checked."
    );
  }
  function curve(_label, stack, unusual) {
    var pts = [];
    var steps = 56;
    var i;
    var a = 22 + stack * 8;
    var b = 30 + stack * 10;
    for (i = 0; i <= steps; i++) {
      var t = -2.6 + (5.2 * i / steps);
      var wave = unusual ? 1 : 1 + 0.035 * Math.sin(t * 8 + stack);
      var x = 110 + Math.cos(t) * a * wave;
      var y = 118 + Math.sin(t) * b * wave;
      if (unusual) {
        x = 110 + Math.cos(t * 0.65) * (a * 0.9);
        y = 78 + Math.sin(t) * (12 + stack * 3);
      }
      pts.push((i === 0 ? "M " : " L ") + x.toFixed(1) + " " + y.toFixed(1));
    }
    return pts.join("");
  }
  function paintLine(link, stack, unusual, broken) {
    var svg = document.getElementById("print");
    if (!svg) return;
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    var klass = "ridge usual";
    if (broken) klass = "ridge broken";
    else if (unusual) klass = "ridge unusual";
    path.setAttribute("class", klass);
    path.setAttribute("d", curve(link.label, stack, unusual || broken));
    svg.appendChild(path);
    var legend = document.getElementById("print-legend");
    if (legend) {
      if (broken) {
        legend.textContent = "Broken link from entry " + link.record_id + ": " + link.label;
      }
      else if (unusual) legend.textContent = "New pattern: " + link.label;
      else legend.textContent = "Same print: " + link.label;
    }
  }
  function pump() {
    if (pumping || !lineQueue.length) return;
    pumping = true;
    var item = lineQueue.shift();
    paintLine(item.link, item.stack, item.unusual, item.broken);
    setTimeout(function () {
      pumping = false;
      pump();
    }, 800);
  }
  function growPrint(data) {
    var stack = {};
    var breakAt = data.chain_ok ? null : data.broken_at;
    data.links.forEach(function (link, index) {
      var unusual = link.mark === "change" || link.mark === "alert";
      var call = link.mark === "call";
      var broken = breakAt != null && link.record_id >= breakAt;
      var next = data.links[index + 1];
      if (call && next && next.mark === "alert" && !broken) {
        drawn[link.record_id] = true;
        return;
      }
      if (!call && !unusual && !broken) return;
      var key = broken ? "broken" : unusual ? "new" : link.label;
      var placed = stack[key] || 0;
      stack[key] = placed + 1;
      if (drawn[link.record_id]) return;
      drawn[link.record_id] = true;
      lineQueue.push({ link: link, stack: placed, unusual: unusual, broken: broken });
    });
    pump();
  }
  function changes(data) {
    var section = node("section", "");
    section.appendChild(node("h2", "", "Changes"));
    var rows = data.changes.map(function (change) {
      var tr = document.createElement("tr");
      tr.appendChild(cell("When", change.ts));
      tr.appendChild(cell("Server", change.server_id));
      tr.appendChild(cell("Tool", change.tool));
      tr.appendChild(cell("What changed", change.detail));
      return tr;
    });
    data.alerts.forEach(function (alert) {
      var tr = document.createElement("tr");
      tr.appendChild(cell("When", alert.ts));
      tr.appendChild(cell("Server", alert.code));
      tr.appendChild(cell("Tool", ""));
      tr.appendChild(cell("What changed", alert.detail));
      rows.push(tr);
    });
    if (!rows.length) section.appendChild(node("p", "empty", "Nothing has changed."));
    else section.appendChild(table(["When", "Server", "Tool", "What changed"], rows));
    return section;
  }
  function tools(data) {
    var section = node("section", "");
    section.appendChild(node("h2", "", "Tools"));
    if (!data.tools.length) {
      section.appendChild(node("p", "empty", "No tools yet."));
      return section;
    }
    var rows = data.tools.map(function (tool) {
      var tr = document.createElement("tr");
      var digest = tool.digest ? tool.digest.slice(0, 12) : "none";
      tr.appendChild(cell("Server", tool.server_id));
      tr.appendChild(cell("Tool", tool.name));
      tr.appendChild(cell("Parameters", tool.parameters.join(", ") || "none"));
      var td = cell("Fingerprint", "");
      var code = node("code", "", digest);
      code.title = tool.digest;
      td.appendChild(code);
      tr.appendChild(td);
      return tr;
    });
    section.appendChild(table(["Server", "Tool", "Parameters", "Fingerprint"], rows));
    return section;
  }
  function calls(data) {
    var section = node("section", "");
    section.appendChild(node("h2", "", "Calls"));
    if (!data.calls.length) {
      section.appendChild(node("p", "empty", "No calls yet."));
      return section;
    }
    var rows = data.calls.map(function (call) {
      var tr = document.createElement("tr");
      tr.appendChild(cell("When", call.ts));
      tr.appendChild(cell("Tool", call.tool));
      tr.appendChild(cell("Outcome", call.outcome));
      tr.appendChild(cell("Duration", call.duration_us + " µs"));
      return tr;
    });
    section.appendChild(table(["When", "Tool", "Outcome", "Duration"], rows));
    return section;
  }
  function patterns(data) {
    var section = node("section", "");
    section.appendChild(node("h2", "", "Normal behavior"));
    section.appendChild(node(
      "p",
      "note",
      "The monitor is learning what normal looks like. It needs " + data.warmup +
      " calls before it can judge. It does not block a tool yet."
    ));
    if (!data.patterns.length) {
      section.appendChild(node("p", "empty", "Nothing learned yet."));
      return section;
    }
    var rows = data.patterns.map(function (pattern) {
      var tr = document.createElement("tr");
      var state = pattern.warmed_up
        ? "ready"
        : "learning " + pattern.observations + " of " + data.warmup;
      tr.appendChild(cell("Tool", pattern.tool));
      tr.appendChild(cell("State", state));
      tr.appendChild(cell("Window", String(pattern.call_count)));
      tr.appendChild(cell("Errors", String(pattern.error_count)));
      tr.appendChild(cell("Value classes", pattern.value_classes.join(", ") || "none"));
      tr.appendChild(cell("Median result size", String(pattern.result_size_median)));
      return tr;
    });
    section.appendChild(table(
      ["Tool", "State", "Window", "Errors", "Value classes", "Median result size"],
      rows
    ));
    return section;
  }
  function showSchema(data) {
    var box = document.getElementById("schema-body");
    if (!box) return;
    if (!data.tools || !data.tools.length) {
      box.textContent = "Not connected.";
      return;
    }
    box.textContent = data.tools.map(function (tool) {
      return tool.schema || tool.name;
    }).join("\\n\\n");
  }
  function showCall(data) {
    var box = document.getElementById("exchange");
    if (!box) return;
    box.hidden = false;
    document.getElementById("ex-schema").textContent = JSON.stringify(data.schema, null, 2);
    document.getElementById("ex-input").textContent = JSON.stringify(data.input, null, 2);
    document.getElementById("ex-output").textContent = JSON.stringify(data.output, null, 2);
  }
  function resetPrint() {
    drawn = {};
    lineQueue = [];
    pumping = false;
    var svg = document.getElementById("print");
    if (svg) while (svg.firstChild) svg.removeChild(svg.firstChild);
    seen = "";
  }
  function tick() {
    fetch("/api/board", { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        refresh(data);
        growPrint(data);
        live.textContent = "Live";
      })
      .catch(function () { live.textContent = "Paused"; });
  }
  function callTool(action) {
    var token = document.body.getAttribute("data-demo-token") || "";
    fetch("/api/call", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CIM-Demo-Token": token
      },
      body: JSON.stringify({ action: action })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.schema !== undefined) showCall(data);
        if (data.cleared) {
          resetPrint();
          var box = document.getElementById("exchange");
          if (box) box.hidden = true;
        } else if (data.tampered || data.unusual) {
          resetPrint();
        }
        tick();
      })
      .catch(function () { live.textContent = "Paused"; });
  }
  tick();
  setInterval(tick, 2000);
  function on(id, action) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", function () { callTool(action); });
  }
  on("call-connect", "connect");
  on("call-normal", "call");
  on("call-new", "change");
  on("call-tamper", "tamper");
  on("call-clear", "clear");
})();
</script>
"""


def render_page(
    board: Board,
    *,
    connected: bool | None = None,
    demo: bool = False,
    demo_token: str = "",
) -> str:
    """Return a full HTML document. Store values in the first paint are escaped."""
    live = bool(board.tools) if connected is None else connected
    token_attr = _e(demo_token) if demo else ""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>CIM monitor</title>",
        "<script>",
        '(function(){try{var t=localStorage.getItem("cim-theme");',
        'if(t==="light")document.documentElement.setAttribute("data-theme","light");}',
        "catch(e){}})();",
        "</script>",
        f"<style>{_CSS}</style>",
        "</head>",
        f'<body data-demo-token="{token_attr}">',
        '<div class="shell">',
        '<header class="top">',
        '<div class="brand">',
        '<p class="word">CIM</p>',
        "<h1>Monitor</h1>",
        "</div>",
        '<div class="actions">',
        '<p class="live"><i class="dot"></i><span id="live-state">Live</span></p>',
        '<button type="button" id="theme">Pearl theme</button>',
        "</div>",
        "</header>",
        f'<div id="live" data-sig="{_e(_signature(board, live))}">{_body(board, live)}</div>',
        '<div class="side-panels" id="side-panels">',
        f"{_mcp_panel(board)}{_skills_panel(board)}",
        "</div>",
        '<section id="mcp-schema">',
        "<h2>MCP schema</h2>",
        f'<pre id="schema-body">{_schema_body(board)}</pre>',
        "</section>",
        '<section id="exchange" hidden>',
        "<h2>Last call</h2>",
        "<h3>Schema</h3>",
        '<pre id="ex-schema"></pre>',
        "<h3>Input</h3>",
        '<pre id="ex-input"></pre>',
        "<h3>Output</h3>",
        '<pre id="ex-output"></pre>',
        "</section>",
        "</div>",
    ]
    if demo:
        parts.extend(
            [
                '<div class="demo-bar" aria-label="Demo controls">',
                (
                    f'<button type="button" id="call-connect"'
                    f"{_connect_attrs(board, live)}>Connect MCP</button>"
                ),
                (
                    f'<button type="button" id="call-normal"{_action_disabled(live)}'
                    f"{_primary(live)}>Use the tool</button>"
                ),
                (
                    f'<button type="button" id="call-new"{_action_disabled(live)}>'
                    "Use it in a new way</button>"
                ),
                (
                    f'<button type="button" id="call-tamper"'
                    f"{_tamper_disabled(board, live)}>Change a past log</button>"
                ),
                (
                    f'<button type="button" id="call-clear"'
                    f"{_clear_attrs(board, live)}>Clear and start again</button>"
                ),
                "</div>",
            ]
        )
    parts.extend([_SCRIPT, "</body>", "</html>"])
    return "\n".join(parts)


def _body(board: Board, connected: bool) -> str:
    return (
        '<div class="board">'
        '<aside class="verdict">'
        f"{_connection(board, connected)}{_headline(board)}{_self_check(board)}"
        f'<div id="warnings">{_alert_inner(board)}</div>'
        "</aside>"
        f"{_rail(board)}"
        '<div id="home">'
        f"{_stats(board)}"
        "<details open><summary>See the list</summary>"
        f"{_changes(board)}{_tools(board)}{_calls(board)}{_patterns(board)}"
        f"{_skill_changes(board)}"
        "</details></div></div>"
    )


def _alert_inner(board: Board) -> str:
    """Inner HTML for #warnings (wrapper already has the id)."""
    if not board.chain_ok:
        where = "unknown" if board.broken_at is None else str(board.broken_at)
        return (
            '<div class="warning" role="status"><strong>Warning.</strong> '
            "An old log was changed. MCP disconnected."
            f"<p>Entry {where} no longer matches. Each later entry depends on the "
            "fingerprint before it, so the rest of the chain cannot be trusted.</p></div>"
        )
    drift = next((alert for alert in board.alerts if alert.code == "mcp_behaviour_drift"), None)
    if drift is None:
        return '<p class="alert-line">No behaviour alert.</p>'
    return (
        '<div class="warning" role="status"><strong>Warning.</strong> '
        "Strange behaviour detected. MCP disconnected."
        f"<p>Input change: {_e(drift.input_change)}</p>"
        f"<p>Output change: {_e(drift.output_change)}</p></div>"
    )


def _schema_body(board: Board) -> str:
    blocks = [tool.schema for tool in board.tools if tool.schema]
    if not blocks:
        return "Not connected."
    return _e("\n\n".join(blocks))


def _stats(board: Board) -> str:
    skill_n = len(board.skills.skills) if board.skills is not None else 0
    skill_alerts = board.skills.total_alerts if board.skills is not None else 0
    cards = (
        (len(board.tools), "MCP tools"),
        (skill_n, "Skills"),
        (len(board.changes), "MCP changes"),
        (len(board.alerts) + skill_alerts, "Alerts"),
    )
    body = "".join(
        f'<div class="stat"><b>{value}</b><span>{label}</span></div>' for value, label in cards
    )
    return f'<div class="stats">{body}</div>'


def _mcp_panel(board: Board) -> str:
    if not board.servers and not board.tools:
        body = '<p class="empty">No MCP servers in this store yet.</p>'
    else:
        lines: list[str] = []
        for server_id in board.servers:
            tools = [t for t in board.tools if t.server_id == server_id]
            names = ", ".join(t.name for t in tools) if tools else "no tools pinned"
            state = "healthy" if tools else "learning"
            lines.append(
                '<div class="skill-line"><div>'
                f"<div>{_e(server_id)}</div>"
                f'<div class="meta">{_e(names)}</div></div>'
                f'<span class="pill {state}">{state}</span></div>'
            )
        body = (
            f'<p class="note">{len(board.servers)} server(s), {len(board.tools)} tool(s), '
            f"{len(board.calls)} recent call(s).</p>{''.join(lines)}"
        )
    return (
        '<section class="panel-block" id="mcp-panel">'
        '<h2 class="panel-title">MCP <span class="tag">servers &amp; tools</span></h2>'
        f"{body}</section>"
    )


def _skills_panel(board: Board) -> str:
    skills = board.skills
    if skills is None or not skills.skills:
        body = '<p class="empty">No skills in this store yet.</p>'
    else:
        summary = (
            f"{len(skills.skills)} installed · {skills.count('healthy')} healthy · "
            f"{skills.count('learning')} learning · {skills.count('warning')} warning"
        )
        lines: list[str] = [f'<p class="note">{_e(summary)}</p>']
        for row in skills.skills:
            obs = row.profile.observations if row.profile is not None else 0
            if row.integrity != "unchanged":
                paths = ", ".join(row.changed_paths) if row.changed_paths else ""
                meta = f"files {row.integrity}" + (f" ({paths})" if paths else "")
            else:
                meta = "files unchanged"
            meta = f"{meta} · {obs} of {WARMUP}"
            width = min(100.0, (obs / WARMUP) * 100.0) if WARMUP else 0.0
            ready = " ready" if row.state == "healthy" else ""
            lines.append(
                '<div class="skill-line"><div>'
                f"<div>{_e(row.name or row.skill_id)}</div>"
                f'<div class="meta">{_e(meta)}</div>'
                f'<div class="bar{ready}"><i style="width:{width:.1f}%"></i></div>'
                f'</div><span class="pill {row.state}">{_e(row.state)}</span></div>'
            )
        body = "".join(lines)
    return (
        '<section class="panel-block" id="skills-panel">'
        '<h2 class="panel-title">Skills <span class="tag">U1</span></h2>'
        f"{body}</section>"
    )


def _primary(on: bool) -> str:
    return ' class="primary"' if on else ""


def _action_disabled(connected: bool) -> str:
    return "" if connected else " disabled"


def _connect_attrs(board: Board, connected: bool) -> str:
    disabled = " disabled" if connected or board.record_count > 0 else ""
    return f"{disabled}{_primary(not connected and board.record_count < 1)}"


def _clear_attrs(board: Board, connected: bool) -> str:
    empty = board.record_count < 1 and not board.tools
    disabled = " disabled" if empty else ""
    return f"{disabled}{_primary(not connected and board.record_count > 0)}"


def _connection(board: Board, connected: bool) -> str:
    if connected:
        shown = ", ".join(tool.name for tool in board.tools[:3])
        more = ""
        if len(board.tools) > 3:
            more = f" and {len(board.tools) - 3} more"
        return f'<p id="connection" class="connection on">Connected. {_e(shown)}{more}.</p>'
    if board.tools or board.record_count:
        return (
            '<p id="connection" class="connection off">'
            "Store loaded. No live demo MCP connection (monitoring only).</p>"
        )
    return '<p id="connection" class="connection off">Not connected. Connect an MCP to begin.</p>'


def _headline(board: Board) -> str:
    if board.empty:
        return (
            '<p class="banner" id="status">Nothing recorded yet. '
            "Start one with <code>cim proxy --db store.sqlite -- &lt;server command&gt;</code> "
            "or load a tool list with <code>cim inventory</code>.</p>"
        )
    if not board.chain_ok:
        where = "unknown" if board.broken_at is None else str(board.broken_at)
        return (
            f'<p class="banner" id="status"><strong class="bad">Record was changed</strong>. '
            f"Entry {where} no longer matches. {_e(board.chain_reason)} "
            "The list below is still shown. Do not trust it until a good copy passes the check.</p>"
        )
    if board.changes:
        noun = "change" if len(board.changes) == 1 else "changes"
        return (
            '<p class="banner" id="status"><strong class="ok">Record is safe</strong>. '
            f"Something new showed up. {len(board.changes)} {noun}.</p>"
        )
    return (
        '<p class="banner" id="status"><strong class="ok">Record is safe</strong>. '
        f"Nothing new since this server was first seen. {board.record_count} entries.</p>"
    )


def _signature(board: Board, connected: bool) -> str:
    ids = ",".join(str(link.record_id) for link in board.links)
    skill_n = len(board.skills.skills) if board.skills is not None else 0
    skill_w = board.skills.count("warning") if board.skills is not None else 0
    return (
        f"{ids}|{board.chain_ok}|{board.broken_at}|{len(board.changes)}|"
        f"{connected}|{len(board.alerts)}|{skill_n}|{skill_w}"
    )


def _self_check(board: Board) -> str:
    if board.empty:
        return '<p class="check">Waiting for a session.</p>'
    if not board.chain_ok:
        where = "unknown" if board.broken_at is None else str(board.broken_at)
        return (
            f'<p class="check bad">Record check failed at entry {where}. '
            "Later entries no longer match the line.</p>"
        )
    return f'<p class="check ok">Record check passed. {board.record_count} entries checked.</p>'


def _tamper_disabled(board: Board, connected: bool) -> str:
    if not connected or board.record_count < 2:
        return " disabled"
    return ""


def _rail(board: Board) -> str:
    waiting = "No calls yet. A line appears each time a tool is used."
    if board.empty:
        waiting = "Nothing here yet."
    return (
        '<aside class="rail"><h2>Activity pattern</h2>'
        '<div class="print-pad">'
        '<svg id="print" class="print" viewBox="0 0 220 260" role="img" '
        'aria-label="Fingerprint forming"></svg>'
        "</div>"
        f'<p class="legend" id="print-legend">{waiting}</p></aside>'
    )


def _changes(board: Board) -> str:
    rows: list[str] = []
    for change in board.changes:
        rows.append(
            "<tr>"
            + _cell("When", _e(change.ts))
            + _cell("Server", _e(change.server_id))
            + _cell("Tool", _e(change.tool))
            + _cell("What changed", _e(change.detail))
            + "</tr>"
        )
    for alert in board.alerts:
        rows.append(
            "<tr>"
            + _cell("When", _e(alert.ts))
            + _cell("Server", _e(alert.code))
            + _cell("Tool", "")
            + _cell("What changed", _e(alert.detail))
            + "</tr>"
        )
    if not rows:
        body = '<p class="empty">Nothing has changed.</p>'
    else:
        body = (
            "<table><thead><tr><th>When</th><th>Server</th><th>Tool</th>"
            f"<th>What changed</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    return f"<section><h2>Changes</h2>{body}</section>"


def _skill_changes(board: Board) -> str:
    changes = board.skills.changes if board.skills is not None else ()
    if not changes:
        body = '<p class="empty">No skill file changes.</p>'
    else:
        rows = []
        for change in changes:
            rows.append(
                "<tr>"
                + _cell("When", _e(change.ts))
                + _cell("Skill", _e(change.skill_id))
                + _cell("Change", _e(change.change))
                + _cell("Path", _e(change.path))
                + "</tr>"
            )
        body = (
            "<table><thead><tr><th>When</th><th>Skill</th><th>Change</th>"
            f"<th>Path</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    return f"<section><h2>Skill changes</h2>{body}</section>"


def _tools(board: Board) -> str:
    if not board.tools:
        body = '<p class="empty">No tools yet.</p>'
    else:
        rows = []
        for tool in board.tools:
            short = tool.digest[:12] if tool.digest else "none"
            params = ", ".join(tool.parameters) or "none"
            rows.append(
                "<tr>"
                + _cell("Server", _e(tool.server_id))
                + _cell("Tool", _e(tool.name))
                + _cell("Parameters", _e(params))
                + _cell("Fingerprint", f'<code title="{_e(tool.digest)}">{_e(short)}</code>')
                + "</tr>"
            )
        body = (
            "<table><thead><tr><th>Server</th><th>Tool</th><th>Parameters</th>"
            f"<th>Fingerprint</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    return f"<section><h2>Tools</h2>{body}</section>"


def _calls(board: Board) -> str:
    if not board.calls:
        body = '<p class="empty">No calls yet.</p>'
    else:
        rows = []
        for call in board.calls:
            rows.append(
                "<tr>"
                + _cell("When", _e(call.ts))
                + _cell("Tool", _e(call.tool))
                + _cell("Outcome", _e(call.outcome))
                + _cell("Duration", f"{call.duration_us} µs")
                + "</tr>"
            )
        body = (
            "<table><thead><tr><th>When</th><th>Tool</th><th>Outcome</th>"
            f"<th>Duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    return "<section><h2>Calls</h2>" + body + "</section>"


def _patterns(board: Board) -> str:
    note = (
        '<p class="note">The monitor is learning what normal looks like. '
        f"It needs {WARMUP} calls before it can judge. It does not block a tool yet.</p>"
    )
    if not board.patterns:
        body = '<p class="empty">Nothing learned yet.</p>'
    else:
        rows = []
        for pattern in board.patterns:
            rows.append(
                "<tr>"
                + _cell("Tool", _e(pattern.tool))
                + _cell("State", _e(_state(pattern)))
                + _cell("Window", str(pattern.call_count))
                + _cell("Errors", str(pattern.error_count))
                + _cell("Value classes", _e(", ".join(pattern.value_classes) or "none"))
                + _cell("Median result size", str(pattern.result_size_median))
                + "</tr>"
            )
        body = (
            "<table><thead><tr><th>Tool</th><th>State</th><th>Window</th><th>Errors</th>"
            "<th>Value classes</th><th>Median result size</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    return f"<section><h2>Normal behavior</h2>{note}{body}</section>"


def _state(pattern: ToolEnvelope) -> str:
    if pattern.warmed_up:
        return "ready"
    return f"learning {pattern.observations} of {WARMUP}"


def _cell(label: str, value: str) -> str:
    return f'<td data-label="{_e(label)}">{value}</td>'


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
