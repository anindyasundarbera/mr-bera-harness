"""Render a usage report as one self-contained HTML file.

No server, no build step, no external requests. The report JSON is embedded in
the document and the CSS and JavaScript are inline, so the file opens from
`file://` on any machine and keeps working offline and years later. A dashboard
that needed a CDN would break the moment the CDN did, and a dashboard that needed
a server would add a network and a mutation surface this project does not have.

The structure is deliberately the shape a live server would return — a single
report object, and a history array — so adding a server later means replacing how
the data is fetched, not how it is rendered.
"""

from __future__ import annotations

import json
from typing import Any

_NAV = "harness"

_CSS = """
:root{color-scheme:light dark;--bg:#fbfbfd;--fg:#16181d;--muted:#5b6270;--line:#e3e6ec;
--card:#fff;--pass:#137a4b;--fail:#b3261e;--unknown:#8a6d00;--chip:#f2f4f8}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e8eaf0;--muted:#9aa3b2;
--line:#262b35;--card:#161a21;--pass:#5fd39b;--fail:#ff8a80;--unknown:#e5c07b;--chip:#1d222b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;
flex-wrap:wrap;align-items:baseline}header h1{margin:0;font-size:19px}
.meta{color:var(--muted);font-size:13px}
main{padding:20px 24px;max-width:1100px}
section{margin-bottom:28px}h2{font-size:14px;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);margin:0 0 10px}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);
border-radius:8px;overflow:hidden}th,td{text-align:left;padding:9px 12px;
border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;
letter-spacing:.05em;color:var(--muted)}tr:last-child td{border-bottom:0}
.status{font-weight:600;font-size:12px;padding:2px 8px;border-radius:999px;white-space:nowrap}
.status.pass{color:var(--pass);background:color-mix(in srgb,var(--pass) 14%,transparent)}
.status.fail{color:var(--fail);background:color-mix(in srgb,var(--fail) 16%,transparent)}
.status.unknown{color:var(--unknown);background:color-mix(in srgb,var(--unknown) 16%,transparent)}
details.finding{margin:6px 0 0}summary{cursor:pointer;color:var(--muted);font-size:13px}
pre{margin:6px 0 0;white-space:pre-wrap;font-size:12.5px;background:var(--chip);padding:8px 10px;
border-radius:6px}
.tiles{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;
min-width:104px}.tile b{display:block;font-size:22px;font-weight:650}
.tile span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.dirty{color:var(--unknown);font-weight:600}
.empty{color:var(--muted);font-style:italic}
footer{padding:16px 24px;color:var(--muted);font-size:12px;border-top:1px solid var(--line)}
"""

_JS = """
// Rendered entirely from the embedded report/history. No network, ever.
(function () {
  var data = JSON.parse(document.getElementById('harness-data').textContent);
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function statusCell(s) { return el('span', 'status ' + s, s); }

  function renderRun(run) {
    var main = document.getElementById('run');
    main.textContent = '';
    var tiles = el('div', 'tiles');
    [['pass', run.counts.pass], ['fail', run.counts.fail], ['unknown', run.counts.unknown]]
      .forEach(function (pair) {
        var t = el('div', 'tile');
        t.appendChild(el('b', 'status ' + pair[0], String(pair[1])));
        t.appendChild(el('span', null, pair[0]));
        tiles.appendChild(t);
      });
    main.appendChild(tiles);

    var byCategory = {};
    run.checks.forEach(function (c) { (byCategory[c.category] = byCategory[c.category] || []).push(c); });
    Object.keys(byCategory).sort().forEach(function (cat) {
      var sec = el('section');
      sec.appendChild(el('h2', null, cat));
      var table = el('table');
      var head = el('tr');
      ['Check', 'Status', 'Detail'].forEach(function (h) { head.appendChild(el('th', null, h)); });
      table.appendChild(head);
      byCategory[cat].forEach(function (c) {
        var tr = el('tr');
        tr.appendChild(el('td', null, c.name));
        var td = el('td'); td.appendChild(statusCell(c.status)); tr.appendChild(td);
        var detail = el('td');
        detail.appendChild(document.createTextNode(c.detail || ''));
        if (c.findings && c.findings.length) {
          var d = el('details', 'finding');
          d.appendChild(el('summary', null, c.findings.length + ' finding(s)'));
          var pre = el('pre');
          pre.textContent = c.findings.join('\\n');
          d.appendChild(pre);
          detail.appendChild(d);
        }
        tr.appendChild(detail);
        table.appendChild(tr);
      });
      sec.appendChild(table);
      main.appendChild(sec);
    });
  }

  function renderHistory(runs) {
    var main = document.getElementById('history');
    main.textContent = '';
    if (!runs.length) { main.appendChild(el('p', 'empty', 'No prior runs recorded.')); return; }
    var table = el('table');
    var head = el('tr');
    ['When', 'Revision', 'Working tree', 'Pass', 'Fail', 'Unknown'].forEach(function (h) {
      head.appendChild(el('th', null, h));
    });
    table.appendChild(head);
    runs.forEach(function (r) {
      var tr = el('tr');
      tr.appendChild(el('td', null, r.generated_at));
      tr.appendChild(el('td', null, (r.commit_sha || '').slice(0, 12) || '—'));
      var tree = el('td');
      if (r.dirty) tree.appendChild(el('span', 'dirty', 'uncommitted changes'));
      else tree.appendChild(document.createTextNode('clean'));
      tr.appendChild(tree);
      ['pass', 'fail', 'unknown'].forEach(function (k) {
        var td = el('td'); td.appendChild(statusCell(k));
        td.appendChild(document.createTextNode(' ' + (r.counts[k] || 0)));
        tr.appendChild(td);
      });
      table.appendChild(tr);
    });
    main.appendChild(table);
  }

  function renderTransitions(changes) {
    var main = document.getElementById('transitions');
    main.textContent = '';
    if (!changes.length) {
      main.appendChild(el('p', 'empty', 'No status changes between recorded runs.'));
      return;
    }
    var table = el('table');
    var head = el('tr');
    ['Check', 'From', 'To', 'When'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    table.appendChild(head);
    changes.forEach(function (c) {
      var tr = el('tr');
      tr.appendChild(el('td', null, c.check));
      var from = el('td'); from.appendChild(statusCell(c.from)); tr.appendChild(from);
      var to = el('td'); to.appendChild(statusCell(c.to)); tr.appendChild(to);
      tr.appendChild(el('td', null, c.at));
      table.appendChild(tr);
    });
    main.appendChild(table);
  }

  renderRun(data.run);
  renderHistory(data.history);
  renderTransitions(data.transitions);
})();
"""


def _escape_html(text: object) -> str:
    """Escape text interpolated into HTML markup.

    Report fields come from repository content — a project name in
    `harness.toml` — so they are untrusted input. Interpolating one into
    `<title>` or `<h1>` unescaped is an injection: a name containing `</script>`
    or `<img onerror=...>` would become markup. Every text field goes through
    this, and a test asserts it.
    """
    import html  # noqa: PLC0415 - only needed for rendering

    return html.escape(str(text), quote=True)


def _escape_for_script(payload: str) -> str:
    """Make JSON safe to embed in a `<script>` element.

    A `</script>` sequence inside a string would end the element early, and HTML
    comments can confuse legacy parsers. Replacing `<`, `>` and `&` with their
    JSON escapes keeps the value identical when parsed while making the byte
    sequence impossible.
    """
    return payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_html(
    run: dict[str, Any],
    history: tuple[dict[str, Any], ...] = (),
    transitions: list[dict[str, Any]] | None = None,
) -> str:
    """Render a self-contained dashboard for one run plus its history."""
    payload = {
        "run": run,
        "history": list(history),
        "transitions": transitions or [],
    }
    embedded = _escape_for_script(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    )

    dirty = (
        '<span class="dirty">working tree has uncommitted changes</span>'
        if run.get("dirty")
        else "working tree clean"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape_html(_nav_title(run))}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>{_escape_html(_nav_title(run))}</h1>
  <div class="meta">
    {_escape_html(run.get("project", ""))} &middot; {_escape_html(run.get("branch", ""))} &middot;
    revision {_escape_html((run.get("commit_sha") or "unknown")[:12])} &middot; {dirty}
  </div>
  <div class="meta">generated {_escape_html(run.get("generated_at", ""))}</div>
</header>
<main>
  <section><h2>Current run</h2><div id="run"></div></section>
  <section><h2>Status changes between runs</h2><div id="transitions"></div></section>
  <section><h2>Run history</h2><div id="history"></div></section>
</main>
<footer>
  A viewer, not an actor: this file runs the checks and records their outcome. It
  executes nothing and mutates nothing. Self-contained by design — no server, no
  network, no external assets.
</footer>
<script id="harness-data" type="application/json">{embedded}</script>
<script>{_JS}</script>
</body>
</html>
"""


def _nav_title(run: dict[str, Any]) -> str:
    project = run.get("project") or "project"
    return f"{project} — harness usage" if project != _NAV else "harness usage"
