---
type: Changelog Entry
id: CHG-2026-010
date: 2026-10-13
kind: added
title: Recorded the remaining build order and the open decisions
summary: Added docs/design/REMAINING_WORK.md, a durable handoff recording which build-order steps are done, the step 4-6 contract, five DecisionRequired items that must not be guessed, and the environment traps that have already cost time.
covers: [MRB]
---

Steps 1–3 of the build order are done; steps 4–6 are not. A handoff that lived
only in a session transcript would be lost, so the state is recorded as a
repository artifact.

## What it records

- **Which steps are done**, which PR landed each, and the entry point each
  provides.
- **The step 4 contract** — the first step rated Medium risk, and the one that
  puts a model in the loop. The constraint is already fixed: `ADR-2026-005` gives
  the harness execution authority and the model proposals only, and §10.1's
  experiment showed schema enforcement is native while **semantics are not**, so
  the effect gates are where the real checking lives.
- **Five `DecisionRequired` items** that must not be answered with a plausible
  default: the budget unit, the PostgreSQL version, the entry-location
  contradiction, the `workflow` scope, and Postgres locality.
- **The traps**, because each has already cost time: location resolved from
  `Path(__file__)` (five occurrences), `MRB_TEST_DSN` falling back to a real DSN,
  `harness ci` gating on session guards, the `gh`-SSH-vs-https credential
  mismatch, an unreadable `~/.ssh/known_hosts`, and the general rule that a green
  local run is not evidence.

Verified against the repositories rather than recalled: the merged PR numbers,
the entry IDs, the scope list from `gh auth status`, and the `harness.toml`
`decisions` path.

Refs: HARNESS-REMAINING-001
