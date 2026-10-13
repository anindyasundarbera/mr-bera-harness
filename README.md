# mr-bera-harness

**A repository that answers questions about itself.**

A codebase is a pile of files that were accurate the day they were written. Ask it
what it is for, why it is shaped that way, or what previous sessions did, and the
answer is a conversation — or a guess. This harness treats the repository as a
**live system**: the answers are artifacts a programme can read, a test can check,
and an agent can be handed verbatim.

> **The LLM proposes; the harness disposes.**

A model returns schema-validated *proposals* and executes nothing. This harness
validates each proposal and performs every mutation with ordinary code, so the
validation surface is testable rather than a model's reasoning. That is what
makes "every action validated" achievable rather than aspirational.

**Why this exists, and how much of it is true today, is stated plainly in
[docs/PURPOSE.md](docs/PURPOSE.md)** — including what has been closed and what it
deliberately does not claim.

## What it does

Most questions an agent asks are lookups wearing a costume — *"which documents
bind this work item?"*, *"is this blocked?"*, *"what changed?"*. The harness
answers those with code, so they never reach a model and never cost tokens.

It also **stops**. When a value is undecided, the resolver exits non-zero and
names the blocker instead of letting an agent proceed on a plausible guess.

And it is **checked**: a document that disagrees with the repository fails
`harness doctor`, a decision that lacks its reasoning fails the entry schema, and
an undecided value stops work with an exit code rather than being filled in with
something plausible. That is what makes these artifacts living rather than prose.

## Install

```bash
pip install -e .
```

That is the whole requirement: **Python ≥ 3.11, `git`, and PyYAML.** No database, no
server and no network — see [docs/design/RUNTIME_DEPENDENCIES.md](docs/design/RUNTIME_DEPENDENCIES.md).
The extras are optional and each fails loudly, with the fix in its message, when
absent: `[postgres]` for the derived index and ledger mirror, `[propose]` for
proposal gating, `[dev]` for development.

```bash
pip install -e ".[dev]"       # to work on the harness itself
```

## Configure

Create `harness.toml` at your project root. Everything project-specific lives
here; the harness hardcodes no paths, no identifier grammar and no registry names.

```toml
[identity]
name = "MyProject"
id_prefix = "MRB"
levels = ["M", "S", "C", "W", "A"]
widths = [2, 2, 2, 2, 2]

[paths]
docs = "docs"
knowledge = "knowledge"
changelog = "knowledge/changelog"
decisions = "knowledge/decisions"

[registries.gaps]
path = "docs/GAP_REGISTER.md"
id_column = "Gap ID"
state_column = "State"

[guards]
branch_prefixes = ["feat", "fix", "docs", "chore", "refactor", "test", "ci"]
protected_branches = ["main", "master"]

[commits]
types = ["feat", "fix", "docs", "chore", "ci", "refactor", "test", "build", "perf", "style", "revert"]
```

## Use

```bash
harness describe              # show the resolved configuration
harness context <WORK-ID>     # the documents that bind a work item
harness conform               # OKF v0.2 conformance of the knowledge bundle
harness query documents       # look things up in the index, not in files
harness compile <WORK-ID> --budget 4000   # compile a bounded prompt + fingerprint
harness index verify          # drop the index, rebuild from git, require identity
harness doctor                # end-to-end health summary
```

### The exit-code contract

| Code | Meaning | Action |
|---|---|---|
| `0` | Resolved | Proceed with the listed documents |
| `2` | Usage or configuration error | Fix the invocation |
| `3` | **A named blocker applies** | **Stop.** Record the blocker. |
| `4` | **Nothing covers this chain** | **Stop.** Record `BlockedDependency`. |

Codes 3 and 4 both halt work and mean different things. `0` with an empty load
is impossible: that case returns `4`, because treating "nothing to load" as
success would let an agent proceed with no grounding at all.

```bash
$ harness context MRB-M06-S14-C02
STOP CONDITIONS (1) — record the blocker, do not guess
  - Configuration Store Technology Unselected  [BlockedOwner]  blocker=CONTROL-STORE-01
      if you guess: The C02 store is chosen wrong and blocks the entire chain.
      must not: Select a database or storage engine for the configuration store.
$ echo $?
3
```

## Library use

```python
from harness import load_config
from harness.routing import resolve_context

config = load_config(".")
result = resolve_context(config, "MRB-M06-S14-C02")
if result.must_stop:
    ...  # do not proceed
```

## Design

| Principle | Where |
|---|---|
| The model proposes; the harness disposes | `docs/design/HARNESS_ARCHITECTURE.md` |
| Constrained decoding is native, not prompt-and-validate | validated experimentally, see §10.1 |
| Git is the source of truth; anything derived is rebuildable | §5 |
| Prevention over detection: remove a capability rather than check it | §7 |
| Chain-of-thought is **not** validatable; output and effect are | §1.1 |

## Status

`v0.1.0`. Build-order steps 1–5 of
[docs/design/HARNESS_ARCHITECTURE.md](docs/design/HARNESS_ARCHITECTURE.md) §9 are
implemented and merged: extraction and a derived index that rebuilds identically
from git; a query API that answers lookups in SQL; a prompt compiler whose
fingerprint binds exactly what was sent; proposal schemas and effect gates that
enforce the rules the architecture enumerates and execute nothing; and a session
ledger in `git notes` that survives a repository copy. **Step 6 — instruction→prompt
— resolves a human instruction to a work item, and asks instead of guessing** when the
answer is not unique. A **usage dashboard** ships alongside. All six build-order
components are implemented. Beyond the build order, **a file can declare the decision
that produced it** — checked against the decision's anchor hash, so a revised decision
flags every implementing file as stale (`harness provenance`).

**What this repository is for, and how much of it is true today, is stated plainly
in [docs/PURPOSE.md](docs/PURPOSE.md)** — including the limitations it still carries.

The PostgreSQL index is optional. Install the extra only if you want it:

```bash
pip install -e ".[postgres]"
export MRB_HARNESS_DSN="postgresql://user:pass@localhost:5432/db"

harness index build     # git -> model -> Postgres
harness index verify    # drop, rebuild from git, require an identical index
harness index status    # what the index currently holds

harness query touching MRB-M06-S07      # which documents cover this scope?
harness query blocked  MRB-M06-S07      # is this blocked?
harness query stops    --state BlockedOwner   # what is blocked, and by what?

harness compile MRB-M06-S01 --budget 4000     # prompt + fingerprint

harness dashboard run       # run the checks, record the run, write .harness/usage.html
harness dashboard history   # list recorded runs, newest first

harness propose schema      # the proposal JSON Schema, for a provider
harness propose gate p.json # validate a proposal and check every effect gate

harness ledger append ...   # record a session entry under git notes
harness ledger verify       # integrity, and the ledger digest

harness intent resolve "work on MRB-M06-S07"   # instruction -> work item, or a question

harness provenance marker ADR-2026-009   # the declaration line, ready to paste
harness provenance check                 # verify every declaration; exit 1 on stale
harness provenance map                   # which files declare each decision
```

`harness query` exits **3** when the index is unreachable, so "no answers" is
never confused with "no DSN". `harness compile` exits `3` blocked, `4` uncovered,
`5` over budget, `2` usage — and never emits a silently-truncated prompt.

## Licence

Proprietary.
