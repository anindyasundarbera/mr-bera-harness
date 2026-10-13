---
type: Decision Record
id: ADR-2026-008
date: 2026-10-13
title: The build rehearsal does not gate on session guards
status: Accepted
decision: Keep the session guards out of the local CI rehearsal, because they refuse a protected branch and would therefore fail the build on the default branch by definition; session activation and build verification are separate gates.
covers: [MRB]
supersedes: []
---

# Context

Fixing `harness ci` (ADR-2026-007) turned its self-check stage back on. That stage
included `harness guards` as a "branch not stacked" check, and the guards
correctly refuse to run on a protected branch (ADR-2026-004). The result:

```
$ harness ci          # on main
  FAIL  branch not stacked  (exit 1)
RESULT: FAILED — selfcheck
```

The tree was fine — wheel, lint, format, `mypy --strict`, tests, OKF conformance,
routing invariants, entry schema, generated indexes and commit convention all
passed. The build was red because of *where* it ran.

The deeper problem is categorical, not positional. `harness guards` answers *"may
a coding session begin here?"* — it refuses a protected branch, a tracked secret,
staged secrets and unresolved conflict markers. That is a **precondition on a
session**. The rehearsal answers *"does this tree build?"* — a property of the
**tree**. Wiring the first into the second makes the build's result depend on
branch position, and "the build fails on `main`" is not a useful outcome for
anything, least of all CI, which runs on `main` by definition and would fail on
every push to it.

# Decision

The session guards are **not** a stage of the local CI rehearsal.

- Session activation stays where ADR-2026-004 put it: a step an agent runs *before
  doing work*, at the start of every session.
- The rehearsal's self-check keeps the checks that are genuine properties of the
  tree: OKF conformance, routing invariants, entry schema, generated-index
  currency, the resolver exit-code contract, and commit convention.
- Two tests pin the separation, so it cannot be re-broken by a later edit.

# Consequences

- The build result is a function of the tree. `harness ci` passes on a feature
  branch **and** on `main`; before this decision it could not pass on `main`.
- **Nothing becomes less guarded.** Branch policy is still enforced at session
  start, which is the one moment it is actionable — a check that fails a build
  tells a human nothing they can act on, and tells an agent nothing about how to
  start work.
- The distinction is now stated in the stage list itself, so a reader meets it
  before re-adding the step.
- Cost: an agent must remember that a green `harness ci` says nothing about
  branch policy. That is what `harness guards` is for, and it is already required
  at session start.

# Alternatives rejected

- **Pass `--branch` a synthetic feature name.** Makes the step pass while checking
  nothing real; a guard that is told what to think is not a guard.
- **Exclude only the branch finding and keep the rest.** Entangles the two gates
  anyway — the remaining guards read staged and working-tree state, which is not
  what a build stage should assert, and it would still fail on a legitimate
  mid-change tree.
- **Drop the guards from the tool.** Rejected: they are load-bearing at session
  start (ADR-2026-004). The fault was the wiring, not the guard.
