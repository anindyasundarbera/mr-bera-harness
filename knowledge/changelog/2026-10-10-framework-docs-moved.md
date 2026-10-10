---
type: Changelog Entry
id: CHG-2026-002
date: 2026-10-10
kind: changed
title: Framework documentation moved into the harness repository
summary: Moved the harness design, format and research documentation plus five framework ADRs out of the consuming repository.
covers: [MRB]
---

The harness's own documentation now lives with the harness:

- `docs/design/HARNESS_ARCHITECTURE.md` — the design
- `docs/design/OKF_MODULE_SYSTEM.md` — the bundle format and exit-code contract
- `docs/design/RESEARCH_DOSSIER.md` — prior art and the reproduced experiments
- `docs/decisions/ADR-2026-001..005` — the decisions that govern the framework

**Two ADRs stayed behind deliberately.** `ADR-2026-006` (trunk-based
development) and `ADR-2026-007` (Conventional Commits) are decisions a consuming
repository makes about *its own* delivery. Moving them would have stranded that
repository's rules in a project it does not own.

Three defects were found while moving:

1. **`validate_all()` ignored configuration.** Its directory defaults were
   module-level constants pointing at one fixed layout, so a repository keeping
   its entries elsewhere was silently validated as *empty* — zero entries, zero
   problems, which reads like success. The defaults now come from `harness.toml`.
2. **The harness's own config pointed at the wrong place** after the move, so
   `doctor` reported 1 entry instead of 6.
3. **Stale cross-references** inside the moved documents pointed at paths that no
   longer existed.

Also retargeted: `OKF_MODULE_SYSTEM.md` documented a set of scripts
(`tools/okf.py`, `tools/okf_context.py`). In the harness those are a package with
one entry point, so its commands now read `harness context`, `harness conform`.

Verified: 250 tests, 80.7% coverage, lint and mypy clean, and `harness doctor`
reports the harness repository clean with 6 entries.
