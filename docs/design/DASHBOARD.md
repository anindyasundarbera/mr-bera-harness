---
id: HARNESS-DASHBOARD-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, REMAINING_WORK.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Usage dashboard

> ID: HARNESS-DASHBOARD-001
>
> Status: **Implemented** — a run viewer shipped with the harness.
>
> Authority: a design document. The decision that it is a viewer and not an actor
> is `ADR-2026-011`.

---

## 1. What it is

A way to see, and keep seeing, how the harness behaves in a repository it is used
in. Point it at any repository the harness is installed into and it runs the
harness's own checks, records the result as a file, and renders one HTML page
showing the current run, how that run differs from the previous one, and the whole
history.

```bash
harness dashboard run       # run the checks, record the run, write .harness/usage.html
harness dashboard render    # re-render from recorded runs (no checks, no git)
harness dashboard history   # list recorded runs, newest first
```

Open `.harness/usage.html` in a browser. There is nothing else to start.

## 2. A viewer, not an actor

`ADR-2026-005` gives the harness every execution and the model none. A dashboard
whose buttons ran things would add a **second executor** and a network surface —
exactly the unpredictable-agent problem the harness exists to prevent. So:

- it runs the harness's existing deterministic checks and nothing else;
- it mutates only its own run records and the rendered file;
- it needs no server, no port and no network — the HTML is self-contained;
- it opens over `file://`, offline, indefinitely.

The architecture's §7 rule applies: prefer the *impossible* class. There is no
control that could perform an action, so no control can be misused.

## 3. What it checks, and where each answer comes from

Every check is **reused** from the code that already owns it. A dashboard that
reported its own idea of health could disagree with `harness doctor`, and two
answers to one question is the drift this project exists to avoid.

| Check | Category | Source |
|---|---|---|
| OKF conformance | documentation | `harness.okf.Bundle.check` |
| routing invariants | documentation | `harness.routing.invariants.validate_routing` |
| entry schema | governance | `harness.entries.generator.validate_all` |
| session guards | governance | `harness.guards.session.run_all` |
| derived index | index | `harness.index.store` (needs a DSN) |
| prompt compiler | compilation | `harness.compile.tokens.UNIT` |
| tests | verification | the project's own `pytest`, in a subprocess |

## 4. `unknown` is a real outcome

The status is **three-valued**. `unknown` is neither a pass nor a failure, and it
is used deliberately:

| Situation | Why `unknown` |
|---|---|
| No PostgreSQL DSN | the store was never inspected; reporting `pass` would claim health nobody observed |
| On a protected branch | the branch guard **correctly** refuses a session here — painting a correct refusal red would train the reader to ignore red |
| No entry directories | nothing configured to check |
| pytest not installed | a missing tool is not a failing test |

A boolean would have to lie about at least one of these. `healthy` is true only
when nothing **failed**; `unknown` does not fail a run, and it never counts as a
pass.

## 5. Provenance is part of the report

A report without provenance is not evidence. Every run records the revision, the
branch, the project, the harness version — and **whether the working tree was
dirty**. A run over uncommitted work is a different claim from a run over a
commit, and the dashboard shows the difference rather than flattening it.

`generated_at` is the only nondeterministic field, and it is recorded as
provenance rather than as a fact about the code. `collect()` accepts an injected
`now` so a report can be reproduced exactly in a test.

## 6. History accumulates; it is never overwritten

One JSON file per run under `.harness/usage/`, following `ADR-2026-001`'s entry
pattern for the same reason: a record is written once and never edited.

- Filenames begin with a fixed-width UTC timestamp, so they **sort
  chronologically** and the newest run is the last file without reading any.
- A same-second collision **adds a file with a counter** rather than replacing
  one — losing a run to a timing coincidence would destroy the thing history is
  for.
- A malformed run file is **reported, not skipped**: silently dropping it would
  make history look shorter than it is, and a missing entry is indistinguishable
  from a run that never happened.

The **"Status changes between runs"** table is the reason to keep history: a check
that was passing and is now failing is the interesting event, and it is invisible
in any single run.

## 7. Self-contained by construction

The rendered file embeds its data as JSON and inlines all CSS and JavaScript. A
test asserts the output contains no `http://`, `https://`, `src=`, `href=`,
`@import` or `<link` — so a dashboard cannot quietly acquire a CDN dependency and
break when the CDN does.

**Every interpolated field is escaped.** Report fields come from repository
content — a project name in `harness.toml` is untrusted input — so a name
containing `</script>` or `<img onerror=...>` would otherwise be injected as
markup. Markup fields are HTML-escaped; the embedded JSON escapes `<`, `>` and
`&`. Both are asserted by tests; the injection was found by one.

The shape — one `run` object, a `history` array, a `transitions` array — is what a
live server would return, so adding one later means changing how the data is
fetched, not how it is rendered. That was a deliberate choice: a server adds a
port, a network and a second executor, none of which is wanted yet.

## 8. Telemetry stays local

`.harness/` is gitignored. Run records are local telemetry, not source, and
committing them would make the dashboard report its own output as a dirty tree on
every subsequent run. `--out <path>` writes a snapshot wherever a reader wants
one.

Run records are deliberately **not** written into the bundle: the index would then
treat each run as a concept.

## 9. What it is not

| Not built | Why |
|---|---|
| A server, a port, a live-updating page | adds a network and a mutation surface; `ADR-2026-011` |
| Buttons that run things | would add a second executor — the model/harness split |
| A history database | one file per run cannot conflict, and is readable with `cat` |
| A trend/metrics claim | the report holds counts and transitions, not measurements; no capacity, cost or performance figure is asserted anywhere |

## 10. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Usage dashboard: report, append-only run store, self-contained renderer, `dashboard run\|render\|history`. |
