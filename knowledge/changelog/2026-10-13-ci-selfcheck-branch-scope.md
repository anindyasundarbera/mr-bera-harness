---
type: Changelog Entry
id: CHG-2026-007
date: 2026-10-13
kind: fixed
title: The build rehearsal no longer fails on the default branch
summary: harness ci ran the session guards, which refuse a protected branch by design, so the build was red on main while every build check passed; the rehearsal now asserts tree properties only.
covers: [MRB]
---

`harness ci` reported `RESULT: FAILED — selfcheck` when run from `main`, while
wheel build, lint, format, `mypy --strict`, the full test suite, OKF conformance,
routing invariants, entry schema, generated-index currency and commit convention
all passed.

## Cause

The self-check stage invoked `harness guards` as a "branch not stacked" check.
`harness guards` is **session activation**, and it correctly refuses a protected
branch (ADR-2026-004). The build was therefore red because of *where* it ran, not
what it contained.

The fault was categorical: a session precondition was wired into a build
verification, making the build's result depend on branch position. Taken to CI —
which runs on `main` by definition — it would have failed every push to the
default branch.

## Fixed

The stage now asserts only properties of the tree: OKF conformance, routing
invariants, entry schema, generated-index currency, the resolver exit-code
contract, and commit convention. Session activation stays where ADR-2026-004 put
it — a step an agent runs before doing work. Nothing is less guarded; branch
policy is still enforced at session start, which is the only moment it is
actionable.

Two tests pin the separation so a later edit cannot silently re-add the step.
The reason is stated in the stage list itself.

**Before:** `harness ci` on `main` → exit 1. **After:** exit 0, with the same
checks passing.

Refs: ADR-2026-008
