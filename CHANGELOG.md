# Changelog

> **Generated file — do not edit by hand.**
> Regenerate with `python3 tools/entries.py generate`.
> The authoritative entries live in `knowledge/changelog/`.

## 2026-10-10

### Changed: Framework documentation moved into the harness repository

*Moved the harness design, format and research documentation plus five framework ADRs out of the consuming repository.*

- **ID:** `CHG-2026-002`  
- **Covers:** `MRB`

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

### Added: Initial harness with a config layer

*Extracted the generic routing, entry, guard and CI tooling into a project-agnostic package driven by harness.toml, with 250 tests.*

- **ID:** `CHG-2026-001`  
- **Covers:** `MRB`

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
