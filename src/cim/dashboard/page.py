"""Render the live status board. The first paint is HTML; the page then polls."""

from __future__ import annotations

import html

from cim.dashboard.board import Board
from cim.mcp.envelope import WARMUP, ToolEnvelope

_CSS = """
:root {
  color-scheme: dark;
  --bg: #0b3048;
  --surface: #0e3c58;
  --ink: #f2f0e9;
  --muted: #d9d6cc;
  --line: rgba(242, 240, 233, 0.16);
  --accent: #b8f12c;
  --accent-ink: #0b3048;
  --intact: #b8f12c;
  --changed: #f2f0e9;
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #f2f0e9;
  --surface: #ffffff;
  --ink: #0b3048;
  --muted: #3d5568;
  --line: rgba(11, 48, 72, 0.14);
  --accent: #b8f12c;
  --accent-ink: #0b3048;
  --intact: #0b3048;
  --changed: #0b3048;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.45 Aptos, "Segoe UI", sans-serif;
  font-variant-numeric: tabular-nums;
}
button, select {
  font: inherit;
  font-weight: 650;
  color: var(--accent-ink);
  background: var(--accent);
  border: none;
  border-radius: 999px;
  padding: 0.45rem 0.95rem;
}
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--intact); outline-offset: 2px; }
.shell { max-width: 76rem; margin: 0 auto; padding: 1.1rem 1.4rem 3rem; }
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 0.75rem; }
.logo {
  width: 2.4rem;
  height: 2.4rem;
  display: grid;
  place-items: center;
  border: 1.5px solid var(--accent);
  border-radius: 50%;
  color: var(--accent);
  font-weight: 700;
}
.word { margin: 0; font-weight: 650; letter-spacing: -0.03em; }
h1 { margin: 0; font-size: 1.7rem; font-weight: 650; letter-spacing: -0.03em; }
.actions { display: flex; align-items: center; gap: 0.6rem; }
.live {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  color: var(--muted);
}
.dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--accent);
}
@media (prefers-reduced-motion: no-preference) {
  .dot { animation: pulse 2s ease-in-out infinite; }
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.banner {
  margin: 1rem 0 0;
  padding: 0.85rem 0;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--line);
  font-size: 1.2rem;
}
.ok { color: var(--intact); }
.bad { color: var(--changed); }
.check { margin: 0.8rem 0 0; font-weight: 650; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.7rem;
  margin-top: 1rem;
}
.stat {
  background: var(--surface);
  border-radius: 1rem;
  padding: 0.8rem 0.9rem;
}
.stat b { display: block; font-size: 1.7rem; line-height: 1.1; }
.stat span { color: var(--muted); }
details { margin-top: 1rem; }
summary { cursor: pointer; font-weight: 650; }
.frame {
  display: grid;
  grid-template-columns: 16rem 1fr;
  gap: 1.5rem;
  align-items: start;
  margin-top: 1.25rem;
}
h2 { margin: 0 0 0.55rem; font-size: 1.15rem; font-weight: 650; }
.rail {
  position: sticky;
  top: 0.75rem;
  padding: 1rem 1rem 0.8rem;
  background: var(--surface);
  border-radius: 1.25rem;
}
.print { width: 100%; height: auto; display: block; }
.ridge {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 520;
  stroke-dashoffset: 520;
  animation: draw 0.9s ease forwards;
}
.ridge.usual { stroke: var(--ink); }
.ridge.unusual { stroke: #e10600; stroke-width: 3.5; }
@keyframes draw { to { stroke-dashoffset: 0; } }
@media (prefers-reduced-motion: reduce) {
  .ridge { animation: none; stroke-dashoffset: 0; }
  .dot { animation: none; }
}
.legend { margin: 0.4rem 0 0; color: var(--muted); font-size: 0.9rem; }
section { margin-top: 1.4rem; }
section:first-child { margin-top: 0; }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border-radius: 1rem;
  overflow: hidden;
}
th, td {
  text-align: left;
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th { color: var(--muted); font-weight: 650; }
code { font-family: "Cascadia Mono", ui-monospace, Consolas, monospace; font-size: 0.85em; }
.note, .empty { color: var(--muted); margin: 0.3rem 0 0; }
@media (max-width: 800px) {
  .shell { padding: 1rem 0.85rem 2rem; }
  .top { display: block; }
  .actions { margin-top: 0.7rem; }
  .stats { grid-template-columns: 1fr 1fr; }
  .frame { grid-template-columns: 1fr; }
  .rail { position: static; }
  table, tbody, tr, td { display: block; width: 100%; }
  thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  tr { border-bottom: 1px solid var(--line); padding: 0.4rem 0.7rem 0.5rem; }
  td { border: none; padding: 0.12rem 0; }
  td::before {
    content: attr(data-label);
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
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
    button.textContent = root.getAttribute("data-theme") === "light" ? "Teal theme" : "Pearl theme";
  }
  applyTheme(savedTheme());
  button.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "light" ? "teal" : "light";
    try { localStorage.setItem("cim-theme", next === "light" ? "light" : "teal"); } catch (e) {}
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
      var code = node("code", "", "cim proxy --db store.sqlite -- <server command>");
      p.appendChild(code);
      p.appendChild(document.createTextNode(" or load a tool list with "));
      p.appendChild(node("code", "", "cim inventory"));
      p.appendChild(document.createTextNode("."));
      return p;
    }
    var strong = node("strong", data.chain_ok ? "ok" : "bad");
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
    return data.links.map(function (link) { return link.record_id; }).join(",") +
      "|" + data.chain_ok + "|" + data.changes.length;
  }
  function refresh(data) {
    var sig = signature(data);
    if (sig === seen) return;
    seen = sig;
    var status = document.getElementById("status");
    if (status) status.replaceWith(headline(data));
    var check = document.querySelector(".check");
    if (check) check.replaceWith(selfCheck(data));
    var home = document.getElementById("home");
    if (!home) return;
    home.replaceChildren();
    home.appendChild(stats(data));
    home.appendChild(detailList(data));
  }
  function stat(value, label) {
    var box = node("div", "stat");
    box.appendChild(node("b", "", String(value)));
    box.appendChild(node("span", "", label));
    return box;
  }
  function stats(data) {
    var wrap = node("div", "stats");
    wrap.appendChild(stat(data.tools.length, "Tools"));
    wrap.appendChild(stat(data.calls.length, "Calls"));
    wrap.appendChild(stat(data.changes.length, "Changes"));
    wrap.appendChild(stat(data.changes.length ? "Yes" : "No", "New pattern"));
    return wrap;
  }
  function detailList(data) {
    var box = document.createElement("details");
    var summary = document.createElement("summary");
    summary.textContent = "See the list";
    box.appendChild(summary);
    box.appendChild(changes(data));
    box.appendChild(tools(data));
    box.appendChild(calls(data));
    box.appendChild(patterns(data));
    return box;
  }
  function selfCheck(data) {
    if (data.empty) return node("p", "check", "Waiting for a session.");
    if (!data.chain_ok) return node("p", "check bad", "Record check failed.");
    return node(
      "p",
      "check ok",
      "Record check passed. " + data.record_count + " entries checked."
    );
  }
  function shapeOf(label) {
    var hash = 0;
    var i;
    for (i = 0; i < label.length; i++) hash = (hash * 33 + label.charCodeAt(i)) % 997;
    return hash;
  }
  function curve(label, stack, unusual) {
    var hash = shapeOf(label);
    var shift = stack * 5;
    var x0 = 28 + (hash % 36) + shift;
    var y0 = unusual ? 200 : 36 + (hash % 24);
    var x1 = 188 - (hash % 28);
    var y1 = unusual ? 36 : 196 - (hash % 20);
    var c1 = unusual ? 24 : 48 + (hash % 70);
    var c2 = unusual ? 196 : 150 - (hash % 40);
    return "M " + x0 + " " + y0 +
      " C " + c1 + " " + (unusual ? 170 : 20) +
      ", " + c2 + " " + (unusual ? 30 : 210) +
      ", " + (x1 + shift) + " " + y1;
  }
  function paintLine(link, stack, unusual) {
    var svg = document.getElementById("print");
    if (!svg) return;
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("class", unusual ? "ridge unusual" : "ridge usual");
    path.setAttribute("d", curve(link.label, stack, unusual));
    svg.appendChild(path);
    var legend = document.getElementById("print-legend");
    if (legend) {
      legend.textContent = (unusual ? "New pattern: " : "Same as before: ") + link.label;
    }
  }
  function pump() {
    if (pumping || !lineQueue.length) return;
    pumping = true;
    var item = lineQueue.shift();
    paintLine(item.link, item.stack, item.unusual);
    setTimeout(function () {
      pumping = false;
      pump();
    }, 800);
  }
  function growPrint(data) {
    var stack = {};
    data.links.forEach(function (link) {
      var unusual = link.mark === "change" || link.mark === "alert";
      var call = link.mark === "call";
      if (!call && !unusual) return;
      var placed = stack[link.label] || 0;
      if (call) stack[link.label] = placed + 1;
      if (drawn[link.record_id]) return;
      drawn[link.record_id] = true;
      lineQueue.push({ link: link, stack: call ? placed : 0, unusual: unusual });
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
      return rows.push(tr);
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
  tick();
  setInterval(tick, 2000);
})();
</script>
"""


def render_page(board: Board) -> str:
    """Return a full HTML document. Store values in the first paint are escaped."""
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
        "<body>",
        '<div class="shell">',
        '<header class="top">',
        '<div class="brand">',
        '<span class="logo">C</span>',
        "<div>",
        '<p class="word">CIM</p>',
        "<h1>Monitor</h1>",
        "</div>",
        "</div>",
        '<div class="actions">',
        '<p class="live"><i class="dot"></i><span id="live-state">Live</span></p>',
        '<button type="button" id="theme">Pearl theme</button>',
        "</div>",
        "</header>",
        f'<div id="live" data-sig="{_e(_signature(board))}">{_body(board)}</div>',
        "</div>",
        _SCRIPT,
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


def _body(board: Board) -> str:
    return (
        f"{_headline(board)}{_self_check(board)}"
        '<div class="frame">'
        f"{_rail(board)}"
        '<div id="home">'
        f"{_stats(board)}"
        "<details><summary>See the list</summary>"
        f"{_changes(board)}{_tools(board)}{_calls(board)}{_patterns(board)}"
        "</details></div></div>"
    )


def _stats(board: Board) -> str:
    new = "Yes" if board.changes else "No"
    cards = (
        (len(board.tools), "Tools"),
        (len(board.calls), "Calls"),
        (len(board.changes), "Changes"),
        (new, "New pattern"),
    )
    body = "".join(
        f'<div class="stat"><b>{value}</b><span>{label}</span></div>' for value, label in cards
    )
    return f'<div class="stats">{body}</div>'


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


def _signature(board: Board) -> str:
    ids = ",".join(str(link.record_id) for link in board.links)
    return f"{ids}|{board.chain_ok}|{len(board.changes)}"


def _self_check(board: Board) -> str:
    if board.empty:
        return '<p class="check">Waiting for a session.</p>'
    if not board.chain_ok:
        return '<p class="check bad">Record check failed.</p>'
    return f'<p class="check ok">Record check passed. {board.record_count} entries checked.</p>'


def _rail(board: Board) -> str:
    waiting = "No calls yet. A line appears each time a tool is used."
    if board.empty:
        waiting = "Nothing here yet."
    return (
        '<aside class="rail"><h2>Activity pattern</h2>'
        '<svg id="print" class="print" viewBox="0 0 220 240" role="img" '
        'aria-label="Fingerprint forming"></svg>'
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
