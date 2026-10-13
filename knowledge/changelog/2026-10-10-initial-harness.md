---
type: Changelog Entry
id: CHG-2026-001
date: 2026-10-10
kind: added
title: Initial harness with a config layer
summary: Extracted the generic routing, entry, guard and CI tooling into a project-agnostic package driven by harness.toml, with 250 tests.
covers: [MRB]
---

Extracted the generic half of the MrBera tooling into an importable framework.

The decisive measurement was coupling: `okf.py`, `local_ci.py` and
`check_commit_convention.py` had **zero** references to MrBera, while
`routing.py` and `validate_routing.py` had 9 and 22. The split followed that
line rather than being imposed on it.

New: `harness/config.py`. Everything project-specific — the identifier grammar,
document locations, registry names, branch policy — is now read from
`harness.toml`. Verified against a consumer that names work items differently
(`TASK-P001-T0002`), which the hardcoded grammar could not have routed.

Three defects were found during the port, each by a test:

1. **Parent chain truncated.** Segment splitting grouped tokens in pairs,
   producing bogus segments like `M06-S07` and stopping the chain at
   `MRB-M06-S07` instead of `MRB-M06` — silently under-selecting context.
2. **`MRB` alone accepted.** The grammar allowed the bare prefix, which names a
   system rather than a unit of work and routes to an empty chain.
3. **Repo-root resolved wrong.** `parents[2]` pointed at `src/`, so the CLI read
   a different tree than a caller passing explicit paths, and `--check` reported
   drift that did not exist.

Four duplicate `main()` entry points were removed. Each shadowed `cli.py` and was
never reached, which is why they showed as uncovered; removing them raised
coverage from 69% to 80%.

250 tests, coverage 80.5%, lint and format clean, and the harness passes its own
`harness doctor`.
