---
type: Changelog Entry
id: CHG-2026-011
date: 2026-10-13
kind: added
title: Usage dashboard — run, record and view the harness in any repository
summary: Added a shipped usage dashboard that runs the harness's existing checks, records each run as a file so history accumulates and status changes are visible, and renders one self-contained HTML page with no server, no network and no new dependency.
covers: [MRB]
---

A way to see, and keep seeing, how the harness behaves in a repository it is
installed into.

```bash
harness dashboard run       # run the checks, record the run, write .harness/usage.html
harness dashboard render    # re-render from recorded runs
harness dashboard history   # list recorded runs
```

## A viewer, not an actor

The request was for "a dashboard or control panel or visualization platform".
"Control panel" is the load-bearing word: controls imply the browser can act,
which would be a **second executor** in a system built on `ADR-2026-005` (the
harness executes, the model does not). So the dashboard runs the harness's
**existing** deterministic checks and nothing else, mutates only its own run
records and the rendered file, and has no control that could be misused. See
`ADR-2026-011`.

That also removes a server, a port, a network and a new dependency: the output is
one self-contained HTML file that opens over `file://`, offline, indefinitely. A
test asserts it contains **no** `http://`, `https://`, `src=`, `href=`, `@import`
or `<link`, so it cannot quietly acquire a CDN dependency.

## Checks are reused, not reimplemented

Every check comes from the module that already owns it — `Bundle.check`,
`validate_routing`, `validate_all`, `run_all`, the index store, the compiler's
unit. A dashboard reporting its own idea of health could disagree with
`harness doctor`, and two answers to one question is the drift this project exists
to avoid.

## `unknown` is a real outcome

The status is three-valued. An unreachable index is not a failing index; a branch
guard that **correctly** refuses a session on `main` must not be painted red, or
red stops meaning anything; a missing pytest is not a failing test. A boolean
would have to lie about at least one.

## History accumulates

One JSON file per run, following `ADR-2026-001` for the same reason: written once,
never edited. Timestamps sort lexicographically, so the newest run is the last
file without reading any; a same-second collision **adds** a file rather than
replacing one; and a malformed record is **reported, not skipped**, because a
missing entry is indistinguishable from a run that never happened.

The payoff is the **"Status changes between runs"** table — a check that was
passing and is now failing is the interesting event, and it is invisible in a
single run. Demonstrated in a fresh consumer: introducing a conformance error
produced `okf conformance: pass → fail` automatically, and reverting it produced
the reverse.

Provenance is recorded per run, including whether the working tree was **dirty** —
a run over uncommitted work is a different claim from a run over a commit.

## Injection found by a test

Report fields flow from repository content into HTML, so a project name is
untrusted input. A test caught a live injection: a name containing `</script>`
was interpolated raw into `<title>`. Every markup field is now HTML-escaped and
the embedded JSON escapes `<`, `>` and `&`; both are asserted.

## Verified

- 33 dashboard tests; `collect()` is reproducible with an injected `now`.
- Rendered and inspected in a browser for both the harness itself and a fresh
  consumer (`JOB-A01-B002` grammar, `kb/` bundle, `specs/` docs).
- Self-containment, escaping, append-only history, collision handling, malformed
  records and transitions all asserted.
- `.harness/` is gitignored: telemetry is local, and committing it would make the
  dashboard report its own output as a dirty tree.

**Tests:** 415 passing without a database; **481 with a live PostgreSQL**,
coverage 91.4%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards`
and `harness ci` all clean.
