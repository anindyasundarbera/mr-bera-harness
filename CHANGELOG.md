# Changelog

> **Generated file — do not edit by hand.**
> Regenerate with `harness entries generate`.
> The authoritative entries live in `knowledge/changelog/`.

## 2026-10-13

### Added: Query API — lookups answered by SQL, not by reading files

*Implemented build-order step 2, a query surface over the derived index; list-valued scope fields are indexed element-wise so a scope query cannot silently select child scopes, and the SQL answers are tested against the Python resolver.*

- **ID:** `CHG-2026-008`  
- **Covers:** `MRB`

Implements build-order step 2 of `HARNESS_ARCHITECTURE.md` §9: *the lookup surface
that replaces file-reading*. Most agent questions are lookups wearing a costume,
and each one answered by code removes tokens and a hallucination surface.

## Commands

| Command | Question it replaces |
|---|---|
| `query documents` | list the corpus |
| `query show <id>` | what does this document say it is? |
| `query search <text>` | which document mentions this? |
| `query links <id> [--direction in\|out]` | what does this depend on? |
| `query touching <work-id> [--field …]` | which documents cover this scope? |
| `query blocked <work-id>` | is this blocked? |
| `query stops [--state …]` | which work items are blocked, and by what? |
| `query decisions [--status …]` | what is decided? |
| `query gaps [--state …]` | what does the gap register hold? |

All accept `--json`; `--dsn` overrides the environment.

## The schema decision

Step 1 stored `covers` as JSON text, so a scope query could only be a substring
match — and `%MRB-M06%` also matches `MRB-M06-S07`. That silently over-selects
every child scope: an agent would be handed documents it believes bind its work
item, with nothing in the output saying otherwise.

List-valued routing fields are now projected **one row per element** into
`document_field_items`, so a scope query is an exact join. `MRB-M06` selects only
documents that name `MRB-M06`. Over-selection is structurally impossible rather
than merely tested for. See `ADR-2026-009`.

The step 1 invariant is untouched: `read_model` still reconstructs from
`document_fields`, so the digest and the rebuild-identity test are unchanged.
`INDEX_SCHEMA_VERSION` is 2.

## Cross-checked, not assumed

`blocked` and `touching` restate logic `harness.routing.resolve` already
implements. A test compares the SQL answers with `resolve_context` over the same
committed model, and a divergence fails — the Python resolver is the reference,
because that is what an agent actually runs.

Verified against a **real consumer** (`mr_bera`, 34 documents, 17 registry
tables) on three work items. The SQL and Python answers matched exactly:

| Work item | Both report |
|---|---|
| `MRB-M06-S07` | `DESIGN-RUBRIC-01`, `EVID-AI-HW-01`, `IMG-DIM-01` |
| `MRB-M06-S14-C02` | `CONTROL-STORE-01` |
| `MRB-M02` | none |

`query stops` on that corpus returns **12** `BlockedOwner` rows in one query —
the join §5.2 says belongs in SQL, which previously meant reading every `Unknown`
concept and correlating by hand.

## Honesty in the exit codes

Without a DSN, a query exits **3** rather than reporting "nothing applies". An
unreachable index and an empty index are different things; conflating them would
hand an agent a false clean bill of health. Usage errors are validated *before* a
connection is attempted, so a mistyped field name reports the field, not a
connection failure.

## A safety defect found and fixed

The database fixtures fell back to `MRB_HARNESS_DSN` — the same variable that
points at a real index — and they call `reset`, which drops the tables. A test run
against that variable therefore **destroyed an indexed consumer project**, which
is exactly what happened once during development. The fixtures now require
`MRB_TEST_DSN` with no fallback, and a test run with only `MRB_HARNESS_DSN` set
leaves the real index intact (verified: all 12 rows survived).

**Tests:** 338 passing without a DSN; **404 with a live PostgreSQL**, coverage
88.2%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and
`harness ci` all clean.

### Fixed: The build rehearsal no longer fails on the default branch

*harness ci ran the session guards, which refuse a protected branch by design, so the build was red on main while every build check passed; the rehearsal now asserts tree properties only.*

- **ID:** `CHG-2026-007`  
- **Covers:** `MRB`

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

### Fixed: The local CI rehearsal runs in the invoking repository again

*harness ci resolved its root from the installed package directory, so 8 of 12 stages failed while its parity check reported success having read nothing; stages now run in the invoking repository and parity reads the workflow.*

- **ID:** `CHG-2026-006`  
- **Covers:** `MRB`

`ci/rehearse.py` was the last module still resolving its own location
(`Path(__file__).resolve().parent.parent`), which points at the installed package
(`.../src/harness`) rather than the repository the command was run in. Its
siblings had already been corrected; the runner was missed.

## Observed, before the fix

From the harness repository root:

```
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
[parity] local stages vs .github/workflows/ci.yml
  missing locally: none      <-- reported success while reading nothing
RESULT: FAILED — package, typecheck, test, selfcheck
```

Eight of twelve steps failed. The parity check was the worse fault: it compared
the pipeline against a job list it had not parsed, so a green local run would
have meant nothing.

## Fixed

- `repo_root()` resolves `Path.cwd()`, matching `guards/session.py`;
  `run_stage` executes there.
- `check_parity` reads the workflow file, and a parity failure now fails the run.
- The `selfcheck` stages name existing commands; `mypy src` matches `ci.yml`; the
  dead `tools/*.py` references are gone.
- `Step.ok_exit_codes` records that a deliberate non-zero exit is a passing
  check, so the rehearsal can assert the `harness context` exit-code contract.

Result: `RESULT: PASSED`, `parity: every CI job has a local stage`.

## Found while fixing it

With the runner correctly executing in the invoking repository, a test that
called `main(["ci"])` from inside pytest recursed forever — the `test` stage runs
pytest. The test now builds a trivial pipeline from the module's own stages and
asserts the runner drives it, without re-entering the suite.

**Tests:** regression tests pin the root and the parity read.

### Added: Extraction and a derived index that rebuilds identically from git

*Implemented build-order step 1 — committed git bytes are extracted with the tested OKF reader into a normalized model with a stable digest, loaded into PostgreSQL as a derived index, and proven rebuild-identical by dropping the database and rebuilding from git.*

- **ID:** `CHG-2026-005`  
- **Covers:** `MRB`

Implements build-order step 1 of `HARNESS_ARCHITECTURE.md` §9: *extraction + index
— parse frontmatter/tables into Postgres; prove rebuild-from-git is identical.*

## What was built

**Extraction** (`harness/extract/`) — a pure function from committed bytes to a
normalized model:

- `model.py` — frozen `Document` / `RegistryTable` / `IndexModel` and
  `model_digest`, SHA-256 over a canonical JSON rendering. No timestamps, no row
  ids, no insertion order, so the same revision always serializes the same.
- `documents.py` — body headings, resolved internal links, and markdown tables.
  Parsing is **reused** from `harness.okf.reader`, not reimplemented.
- `source.py` — `git archive <rev>` materialized into a temporary tree, then read.
  Extraction therefore sees committed content only.

**Index** (`harness/index/`) — a derived PostgreSQL store. `reset` drops and
recreates the tables; `write_model` writes a model; `read_model` reconstructs one
**from the rows alone**, never touching the filesystem.

**CLI** — `harness index build | verify | status`, returning 3 when PostgreSQL is
unreachable, in keeping with the existing exit-code contract.

## The invariant

The test drops the tables, rebuilds from git, and requires the two models'
digests to be identical *and* compares them table-by-table. It also asserts the
model is non-empty and that a committed change **breaks** the equality — without
those, it could pass while indexing nothing. A hand-run negative control
corroborated it: corrupting one stored field changed the digest
(`73c167aa…` → `f1b349f5…`).

Verified against a real PostgreSQL, not only against the store in isolation.

## Notes

- **A defect CI caught that a local run could not.** The git-backed fixtures
  initially ran `git commit` relying on the host's global identity. That exists on
  a developer machine and not on a runner, so the tests passed locally and failed
  in CI with `Author identity unknown` (exit 128) on all three Python versions.
  The fixtures now supply an identity explicitly (a local `user.name`/`user.email`
  plus the environment). Reproduced with `GIT_CONFIG_GLOBAL=/dev/null
  GIT_CONFIG_SYSTEM=/dev/null HOME=<empty>`, which is now the shape this work is
  verified against.
- `psycopg` stays an optional extra, the index tests skip cleanly without a DSN,
  and no PostgreSQL version is asserted — no authoritative document fixes one.
- Registry files are read from `[registries.*]` in `harness.toml`; the harness
  never guesses which documents are registries.
- Paths resolve from the invoking directory. Resolving a caller's context from
  the library's own location is a defect this repository has hit repeatedly.

**Tests:** 329 passing (15 skipped without a DSN); 344 passing against a live
PostgreSQL, coverage 87.9% against an 80% floor. Lint, format, `mypy --strict`,
`harness doctor` and `harness ci` all clean.

## 2026-10-10

### Fixed: Git commands run in the invoking repository, not the package's directory

*Both the commit-convention check and the guards resolved their repository root from the package's own location, so run from a consumer they failed or operated on the wrong repo.*

- **ID:** `CHG-2026-004`  
- **Covers:** `MRB`

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

### Fixed: Wire the missing subcommands, and stop writing into the wrong repository

*Four capabilities were unreachable from the CLI after the entry points were consolidated, and generated indexes were written into the harness repo instead of the invoking project.*

- **ID:** `CHG-2026-003`  
- **Covers:** `MRB`

Two defects that only surfaced once a consumer actually depended on the harness.

**Four subcommands were missing.** Consolidating the duplicate `main()`
functions into one entry point removed the only way to run the guards, the
commit-convention check, the entry validator and the CI rehearsal. `AGENTS.md`
instructs agents to run the guards, so their absence was silent: the command
simply did not exist. All four are now wired in, and a test asserts that every
capability the documentation names is reachable.

**Generated files were written into the harness repository.** The output path for
`CHANGELOG.md` and `docs/DECISIONS_INDEX.md` derived from
`Path(__file__).resolve().parents[3]` — the package's own location. Running
`harness entries generate` inside a consumer therefore wrote into the *harness's*
working tree, silently modifying a different project. The path now derives from
the invoking directory.

Coverage rose from 74% to 89% once the subcommands were tested, which is itself
evidence that they had been untested.

274 tests, 89.4% coverage.

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
