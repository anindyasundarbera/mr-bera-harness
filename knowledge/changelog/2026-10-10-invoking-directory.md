---
type: Changelog Entry
id: CHG-2026-004
date: 2026-10-10
kind: fixed
title: Git commands run in the invoking repository, not the package's directory
summary: Both the commit-convention check and the guards resolved their repository root from the package's own location, so run from a consumer they failed or operated on the wrong repo.
covers: [MRB]
---

`commits.py` and `guards/session.py` resolved their repository root from
`Path(__file__).resolve().parent.parent` — the harness's *installation*
directory. Run from a consumer, `git` then executed there and failed with
`fatal: not a git repository`.

This is the third defect of the same class, and the pattern is worth naming:
**a library must never resolve the caller's context from its own location.**
The other two were the generated-index output path (wrote into the harness repo)
and `validate_all()`'s default directories (silently validated a consumer as
empty).

It reached CI because the harness's own tests always run from the harness's own
directory, where the two paths coincide. A regression test now asserts the root
from a *different* directory, which is the only condition that exposes it.

278 tests, 89.4% coverage.
