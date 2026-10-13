---
type: Decision Record
id: ADR-2026-011
date: 2026-10-13
title: The usage dashboard is a static viewer, not a live actor
status: Accepted
decision: Ship the usage dashboard as a self-contained static HTML file that runs the harness's existing deterministic checks and records their outcome, with no server, no network, no new dependency and no control that can perform an action.
covers: [MRB]
supersedes: []
---

# Context

The owner asked for a dashboard to track how the harness behaves across the
repositories that use it — "a browser based dashboard or control panel or
visualization platform, which could also be shipped along with the harness".

The phrase "control panel" carries an assumption worth making explicit. A panel
implies controls, and controls imply the browser can act. That would be a second
executor: `ADR-2026-005` gives the harness every mutation and the model none, and
`HARNESS_ARCHITECTURE.md` §7 says to prefer removing a capability over checking
for its misuse. A dashboard with action buttons is precisely the misuse surface
the harness exists to eliminate, and it would add a listening port, a network and
an auth question to a package whose current answer to all three is "none".

Two questions had to be settled together:

1. **Does it act?** If yes, it is a control plane and needs the full
   precondition/approval machinery — a much larger thing, and not obviously wanted.
2. **Does it need a server?** A server adds a dependency, a port and a network;
   a static file adds none, and keeps working offline and years later.

The owner chose: a static dashboard now, structured so a live server can be added
later without rework.

# Decision

**A viewer, not an actor.**

- It runs the harness's **existing** deterministic checks and records their
  outcome. Every check is reused from the module that already owns it, so the
  dashboard cannot report a different answer from `harness doctor`.
- It mutates only its own run records and the rendered file. It has no control
  that could perform an action, so no control can be misused.
- The output is **one self-contained HTML file**: data embedded as JSON, CSS and
  JavaScript inline, no external asset. It opens over `file://`, offline.
- **No new dependency.** The standard library is sufficient for a static file.
- Run records are **one file per run** under `.harness/`, following
  `ADR-2026-001`'s pattern: append-only, never overwritten, sortable by filename,
  and a malformed record is reported rather than skipped.
- The rendered data shape — one `run` object, a `history` array, a `transitions`
  array — is the shape a live server would return, so adding one later changes how
  the data is fetched, not how it is rendered.

# Consequences

- **The shipped artifact has no runtime.** Copy it, mail it, open it in five
  years: it works, because it needs nothing.
- **No second executor exists.** This is the §7 "impossible" class: there is no
  action to take, so there is no action to check.
- **`unknown` is a first-class status.** A boolean would have to call an
  uninspected index or a correct branch-guard refusal either a pass or a failure,
  and both would be lies. Three values cost one more case in the renderer and
  remove a class of false reports.
- **Provenance is recorded**, including whether the tree was dirty. A report over
  uncommitted work is a different claim from one over a commit.
- Cost: no live updating. A reader runs the command, then opens the file. For a
  check suite that takes seconds, that is not a real cost.
- Cost: history is per-checkout, not central. Aggregating across repositories is
  a genuine later feature, and it wants a server — which is exactly the rework
  this decision keeps open rather than forecloses.
- Security: because fields flow from repository content into HTML, **every
  interpolated field is escaped**. A project name is untrusted input; a test found
  the injection before it shipped.

# Alternatives rejected

- **A local server with action buttons.** Adds a port, a network, an auth
  question and a second executor, to answer questions that a file answers.
  Rejected as disproportionate to the need, not as impossible.
- **A static file but with a build step** (a bundler, a template engine). Adds a
  dependency and a toolchain for a single page whose only dynamic content is an
  embedded JSON blob.
- **Writing the dashboard into the bundle.** The index would treat each run as a
  concept; run records are telemetry, not knowledge.
- **Committing run records.** The dashboard would then report its own output as a
  dirty tree on every run.
- **Rendering with an LLM summary.** The architecture's §4 rule: keep the model
  out of the hot path. A summary would be a probabilistic claim over deterministic
  facts, and the facts are already one table away.
