# Changelog

> **Generated file — do not edit by hand.**
> Regenerate with `harness entries generate`.
> The authoritative entries live in `knowledge/changelog/`.

## 2026-10-13

### Added: Recorded the runtime dependency audit

*Audited and documented what the harness needs to run on any device or container, proving in a venv containing only PyYAML that no database, server or network is required and that every optional capability fails loudly with the fix in its message.*

- **ID:** `CHG-2026-015`  
- **Covers:** `MRB`

The harness is meant to run wherever a coding agent runs, so the requirement was
audited rather than asserted. `docs/design/RUNTIME_DEPENDENCIES.md` records the
result.

## What was measured

An AST scan of every module finds exactly **three** third-party imports — `yaml`,
`jsonschema`, `psycopg` — and only `yaml` is core. Nothing under `src/` imports
`socket`, `http`, `urllib`, `ssl`, `asyncio` or `requests`: the harness never
reaches the network. The only external binary invoked anywhere is **`git`**.

A venv created with `pip install -e .` and **nothing but PyYAML** was run against a
real consumer project. Every command that does not need an extra worked fully:
`doctor`, `conform`, `context`, `guards`, `commits`, `entries`, `compile` and the
whole ledger. The two that do need one refused with the fix in the message —
`propose validate` named `pip install -e '.[propose]'`, and `index status` named
`MRB_HARNESS_DSN` and exited 3.

Notably, `harness.propose`, `harness.index` and `harness.ledger` all **import** with
no extras installed, because each defers its third-party import to the call that
needs it. A missing extra can therefore never break an unrelated command.

## The answer

A container needs `python>=3.11`, `git`, and `pip install mr-bera-harness`. The
database is optional and derived; there is no server, no daemon and no network
dependency. A repository with no database still has a complete document model and a
complete session ledger, because the facts live in git.

The audit also records its own limits: Python ≥ 3.11 is a declared floor (tested on
3.11–3.14; CI covers 3.11–3.13), and `git` is assumed present because a git
repository is the premise rather than a dependency that could sensibly degrade.

Refs: HARNESS-RUNTIME-001

### Added: Session ledger — what was sent, proposed, decided and observed

*Implemented build-order step 5, recording each session as an append-only entry in git notes bound to its commit, with an optional Postgres mirror derived from the notes and proved rebuild-identical.*

- **ID:** `CHG-2026-014`  
- **Covers:** `MRB`

Implements build-order step 5 of `HARNESS_ARCHITECTURE.md` §9: *`git notes` +
Postgres; prompt, proposal, verdict, effect.*

```bash
harness ledger append --work-id MRB-M06-S01 --prompt-fingerprint <sha256> \
    --budget 4000 --unit word --proposal p.json --gate --effect applied
harness ledger list | show | verify | mirror | transport
```

## Where the record lives, and why

§5.3 gives the reasoning — git is already an append-only, content-addressed,
cryptographically ordered log with a distributed transport, and `git notes` adds
metadata without rewriting history. A record attached to a commit therefore
**survives a repository copy**, the property §10 names as the reason to prefer
notes over Postgres alone.

**A limitation, measured rather than assumed:** a `git notes` ref is **not** carried
by a plain clone or fetch. Records travel only when the ref is transported
explicitly, which `harness ledger transport` prints. This matters — a ledger that
appeared complete locally and silently lacked remote entries would be worse than no
ledger. The CLI prints the commands rather than executing them: pushing is a
separate authorised action.

## The prompt is recorded by reference

Step 3's fingerprint already binds the prompt bytes *and* the manifest of what is in
it, so the ledger stores the fingerprint, budget, unit and entry count — never the
text. Storing the prompt again would be a second copy to keep in step with the
compiler.

## The ledger records; it does not execute

§9 lists "effect" as a recorded field. The ledger has no executor, so it cannot
observe one: it records what the caller reports, and the default is
`not-observed` — the truthful value for a recorder that was not told. An invented
effect would be the ledger claiming knowledge it does not have.

Asserted from the source, not asserted in prose: every `subprocess` call is a
**literal git command** (so nothing built from a record can reach a shell), no
write/delete call exists outside git's own notes, and appending leaves the working
tree byte-identical — a ledger that dirtied the tree would make every later run
report a dirty tree.

## The mirror is derived, and provably so

Written from the notes and nothing else; resets first, so it is a rendering of the
current ledger rather than an accumulation — a record removed from the notes
disappears from the mirror rather than lingering as a fact git does not hold. Each
row stores both the queryable columns and the whole record, because storing only the
columns would make the invariant **unprovable by construction**. Drop it, rebuild
from the notes, digests identical — the step-1 pattern, reused.

A repository with no database still has a complete ledger.

## Two design faults found while building

1. **The mirror could never have proved its own invariant.** The first version
   stored only the queryable columns, so a rebuilt record could not equal the source
   record it came from. Caught before it shipped; the row now carries the whole
   record as canonical JSON alongside the columns.
2. **`mirror` was both a function and a submodule name.** `from harness.ledger
   import mirror` was ambiguous — a footgun for a caller. The function is now
   `write_mirror`.

**Tests:** 513 without a database; **585 with a live PostgreSQL**, coverage 91.1%.
Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and `harness ci`
all clean; CI matrix and the CI shape both pass.

### Added: Proposal schemas and effect gates — what may be proposed, and what is refused

*Implemented build-order step 4, a versioned JSON Schema for proposals plus gates that enforce the six rules architecture 7.1 enumerates, returning a three-valued verdict and never executing anything.*

- **ID:** `CHG-2026-013`  
- **Covers:** `MRB`

Implements build-order step 4 of `HARNESS_ARCHITECTURE.md` §9: *what the model may
propose, and how a proposal is checked*. The first step with a model in the loop —
and the one where the propose/dispose split becomes code rather than a diagram.

```bash
harness propose schema                  # the JSON Schema, for a provider
harness propose validate proposal.json  # structure only
harness propose gate proposal.json      # structure + every policy
```

## The §10.1 split, demonstrated rather than described

Structure is the provider's job; meaning is the harness's. §10.1 established that
constrained decoding enforces the schema at the sampling layer and that
**semantics are not enforced** — every adversarially steered model returned a
*valid* proposal.

The code shows the gap. This proposal is **fully schema-valid** and still refused:

```
$ harness propose validate …   → exit 0   (the provider would allow it)
$ harness propose gate …       → exit 2   (refused: `main` is a protected branch)
```

`1` (structurally invalid) and `2` (refused) are distinct exit codes for exactly
this reason: conflating structure with meaning hides the second case.

## The policies are the architecture's own rules

The `intent` enum is derived from the rules §7.1 already enumerates; each gate
cites the rule it enforces; a test asserts all six are covered, so a rule cannot
be dropped and a policy cannot be invented. The schema also enforces each intent's
required fields **conditionally**, so a `write_file` with no work packet is
structurally invalid — a stronger form of the rule than a gate that refuses it.
`additionalProperties: false` stops a key being smuggled in.

One mechanism the architecture does not enumerate but which makes
`never commit a secret` real: **a path may not escape the project root**.
Normalizing first is what closes `knowledge/../../.env`.

## Three-valued verdicts, and `not-checked` blocks

`permitted` / `refused` / `not-checked`, and `may_execute` is true only when every
gate is `permitted`. A session that declared no change manifest cannot be checked
against `one logical change per branch`, so a write reports `not-checked` and does
not proceed — the omission becomes visible instead of being assumed compliant.

The gate judges the branch a proposal **names**, not the branch the session is on:
creating `feat/x` is the intent that leaves a protected branch, while creating a
branch *called* `main` is refused. Refusing to *start* on a protected branch
remains the session guard's job (`ADR-2026-004`) rather than a second answer here.

## Nothing executes

There is no code path from a verdict to a mutation — asserted, not asserted-in-
prose: a test checks that neither module imports `os`, `subprocess`, `shutil`,
`socket`, `urllib` or `requests`, calls no write method, and that gating the same
proposal three times leaves the tree byte-identical.

## One new optional dependency

`jsonschema` via `.[propose]`, the standard implementation of the format §10.1
names. A hand-rolled subset would be a second definition of validity that drifts
from the provider's and fails at the boundary instead of in a test. A missing
validator is a **loud failure, never a silent pass**; the tests skip cleanly
without the extra (verified in a venv that omits it), and CI installs it.

## Two bugs found by the tests

1. **The gate permitted creating a branch called `main`.** It had special-cased
   `create_branch` on a protected branch, conflating the branch *named* with the
   branch *occupied*. Corrected, and the two cases are now separate tests.
2. **A manifest of `.` did not cover every path**, because `.env.example` is not
   prefixed by `"./"`. Corrected, with a test for the whole-project case.

**Tests:** 482 without a database; **548 with a live PostgreSQL**, coverage 91.5%.
Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and `harness ci`
all clean; CI matrix and the CI shape both pass.

### Changed: Parked build-order step 4 by owner instruction

*Recorded in the handoff that step 4 (proposal schemas + effect gates) is parked and must not be started without an explicit owner request, so a later session treats it as an instruction rather than a judgement call.*

- **ID:** `CHG-2026-012`  
- **Covers:** `MRB`

The owner parked step 4 and will request it explicitly when wanted. An unrecorded
"park" is exactly the transient instruction that the handoff document exists to
make durable: the next session reads the build order, sees step 4 marked as next,
and starts it.

`docs/design/REMAINING_WORK.md` §2 now carries a **PARKED** notice stating that an
agent must not begin step 4, speculatively prepare it, or prepare a branch for it,
and that starting it would be a violation rather than a judgement call. The
already-decided contract for the step is kept below the notice so the eventual
session builds against it instead of re-deriving it.

Nothing else changed: steps 5 and 6 remain not started, and the six
`DecisionRequired` items are unchanged.

Refs: HARNESS-REMAINING-001

### Added: Usage dashboard — run, record and view the harness in any repository

*Added a shipped usage dashboard that runs the harness's existing checks, records each run as a file so history accumulates and status changes are visible, and renders one self-contained HTML page with no server, no network and no new dependency.*

- **ID:** `CHG-2026-011`  
- **Covers:** `MRB`

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

### Added: Recorded the remaining build order and the open decisions

*Added docs/design/REMAINING_WORK.md, a durable handoff recording which build-order steps are done, the step 4-6 contract, five DecisionRequired items that must not be guessed, and the environment traps that have already cost time.*

- **ID:** `CHG-2026-010`  
- **Covers:** `MRB`

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

### Added: Prompt compiler — a work item in, a bounded prompt and a fingerprint out

*Implemented build-order step 3, compiling a task ID plus a caller-supplied budget into a deterministic prompt with a SHA-256 fingerprint that binds its content; over-budget and blocked work items are refused rather than truncated.*

- **ID:** `CHG-2026-009`  
- **Covers:** `MRB`

Implements build-order step 3 of `HARNESS_ARCHITECTURE.md` §9: *task ID +
selection + budget → prompt + fingerprint*. Deterministic — no model, no clock,
no network.

## What it does

Selection comes from `harness.routing.resolve`; text comes from the same
`git archive` materialization step 1 introduced, so the prompt is a **pure
function of a committed revision**. `harness compile <work-id> --budget N` prints
the prompt on stdout and the fingerprint on stderr, so a caller can capture either
without the other. `--json` carries both; `--manifest` carries the audit record
without the text.

## The fingerprint is the §3 dashed edge, made executable

The architecture calls the pre-call fingerprint *load-bearing*: without it a
session cannot be reproduced and "deterministic" is an unevidenced claim. The
digest covers the prompt text **and the manifest** of which documents are in it —
concept id, path, title, read budget, trust tier, status, staleness, coverage and
per-entry size.

Hashing the text alone would let a same-length document be substituted without the
digest changing. A test asserts the structure binds.

## No invented threshold

`--budget` is **required with no default**. No authoritative document fixes a
value, and a default would silently become part of every fingerprint. The unit is
an exact **word** count, named in `harness.compile.tokens.UNIT` — deterministic
and provider-independent, which is what a reproducible compiler needs. It is not
called a "token", because a token depends on the model's tokenizer and would make
the budget provider-specific. Adopting a tokenizer is recorded as
`DecisionRequired` in `ADR-2026-010`.

The budget bounds admissibility, not content, so it does **not** enter the
fingerprint: a generous and a tight budget compile the same prompt.

## Refusal, not truncation

| Condition | Exit |
|---|---|
| blocked | `3` |
| nothing covers the chain | `4` |
| over budget | `5` |
| usage error | `2` |

Over budget is all-or-nothing on purpose. Dropping documents would be a **false
claim** about what binds the work item, and the failure is invisible — the model
would answer confidently from partial context. `harness context` remains available
for discovery. `--defining` is passed through, so a concept whose `do_not_use_for`
names a state the caller intends to define appears in the manifest as **excluded**
rather than vanishing.

## Verified

- 35 compiler tests and 9 CLI tests: determinism, fingerprint binding, every
  refusal path, exclusion, manifest.
- Same revision compiles byte-identical text and fingerprint; an uncommitted edit
  changes neither; a committed edit changes both.
- Real consumer corpus: `MRB-M06-S01` compiles 10 documents / 2582 words /
  fingerprint `395fe52f…`, **identical across runs**; `MRB-M06-S07` refuses with
  exit 3 naming `DESIGN-RUBRIC-01`, `EVID-AI-HW-01`, `IMG-DIM-01`.
- A malformed work identifier is reported as a usage error rather than escaping as
  an uncaught `OkfError` — found by a test, fixed.

**Tests:** 382 passing without a database; **448 with a live PostgreSQL**,
coverage 91.3%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards`
and `harness ci` all clean.

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

## CI now runs a database, because the coverage floor said so

The first CI run of this branch failed **all three test jobs while every test
passed** (`338 passed, 66 skipped`). The cause was the coverage floor:

```
FAIL Required test coverage of 80.0% not reached. Total coverage: 79.02%
```

Requiring a separate test DSN also meant CI skipped the whole derived-store layer
— ~350 statements in the modules this step adds — so the floor was being enforced
against code CI never ran. Both symptoms have one cause.

The `test` job now runs a `postgres:16` service and installs the `postgres`
extra, so the index and query tests execute instead of skipping. Coverage rises
from 79% to **91%** as a side effect, which is the honest measure: the code is
now actually exercised rather than excluded.

Two alternatives were rejected. Silencing the derived-store modules in the
coverage config would raise the number by measuring less — the opposite of what a
floor is for. Lowering the floor below 80% would make the number pass while
leaving the layer untested. Neither makes anything more correct.

Verified locally against both DSN states before pushing: **338 passed** without a
database, **404 passed / 91.16%** with one. The rehearsal (`harness ci`) runs no
coverage gate, so it is green either way.

**Tests:** 338 passing without a DSN; **404 with a live PostgreSQL**, coverage
91.2%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and
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
