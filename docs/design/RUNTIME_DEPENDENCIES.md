---
id: HARNESS-RUNTIME-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, SESSION_LEDGER.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Runtime dependencies

> ID: HARNESS-RUNTIME-001
>
> Status: **Audited** — what the harness needs to run, measured rather than assumed.
>
> Authority: a design document recording an audit. It creates no decision.

---

## 1. The question

The harness is meant to run on any device or container where a coding agent runs. So:
what must be present for it to work, and what happens when something is missing?

Every claim below was **measured** in a venv containing nothing but the core
requirement, on a real consumer project.

## 2. The complete list

| Requirement | Kind | Needed for | Absent means |
|---|---|---|---|
| **Python ≥ 3.11** | runtime | everything | cannot install |
| **`git`** on `PATH` | runtime | routing, extraction, guard, ledger, commit check | those commands fail |
| **PyYAML ≥ 6.0** | dependency | reading frontmatter | nothing works |
| `jsonschema` | extra `[propose]` | gating proposals | one command refuses, with the fix in its message |
| `psycopg` | extra `[postgres]` | the derived index and mirror | index/query commands refuse |
| `pytest`, `ruff`, `mypy` | extra `[dev]` | development only | not needed at runtime |

There is no fourth third-party import. An AST scan of every module finds exactly
`yaml`, `jsonschema` and `psycopg`, and only `yaml` is core.

## 3. What is *not* required

| Not required | Evidence |
|---|---|
| **A database** | with only PyYAML installed, `doctor`, `conform`, `context`, `guards`, `commits`, `entries`, `compile`, `propose schema`, `ledger list/append/transport` and `dashboard` all exit 0 |
| **A network** | no module under `src/` imports `socket`, `http`, `urllib`, `ssl`, `asyncio` or `requests`. The harness never reaches out. |
| **A server or daemon** | the dashboard is one static HTML file; the index is a CLI command |
| **Docker, Postgres, Redis** | Postgres is optional and derived; nothing else exists |
| **`git notes` refs to be pushed** | the ledger is local until the owner transports the ref (documented, `ADR-2026-013`) |

**The database is optional.** `psycopg` is an extra, and `harness index` and
`harness query` refuse cleanly without it:

```
$ harness index status          # no DSN, no psycopg
ERROR: no PostgreSQL DSN provided (set MRB_HARNESS_DSN or pass --dsn)
The index is a derived store; set MRB_HARNESS_DSN or pass --dsn.
exit 3
```

That is the designed behaviour, not a failure: the index is a derived store
(`ADR-2026-006`), git holds the facts, and a repository with no database still has
a complete document model and a complete session ledger.

## 4. What a missing optional piece looks like

Every optional capability fails **loudly, with the fix in the message**, and never
half-works:

```
$ harness propose validate p.json      # no jsonschema
ERROR: no JSON Schema validator installed. Proposals are validated against JSON
Schema, so install the extra: pip install -e '.[propose]'
exit 4
```

No command silently degrades. An unreachable store is never reported as "nothing
found" — `harness query` exits 3, distinct from an empty result, so an agent cannot
mistake "I could not look" for "there is nothing there".

## 5. The measured result

A venv created with `python -m venv` and `pip install -e .` — **nothing but
PyYAML** — run against a real consumer project:

| Command | Exit | Note |
|---|---|---|
| `describe` `doctor` `conform` `context` `guards` | 0 | full function |
| `commits` (valid / invalid message) | 0 / 1 | full function |
| `entries validate` | 0 | full function |
| `compile MIN-A01 --budget 100` | 0 | produced a fingerprint |
| `ledger list` `ledger append` `ledger transport` | 0 | full function — notes are git, not a database |
| `dashboard run` `dashboard history` | 0 | full function, including the rendered HTML |
| `propose schema` | 0 | the schema is a constant |
| `propose validate` | 4 | refuses; message names the extra |
| `index status` `query documents` | 3 | refuses; message names `MRB_HARNESS_DSN` |

Every optional module **imports** with no extras installed — `harness.propose`,
`harness.index` and `harness.ledger` all load, because each defers its third-party
import to the call that needs it. So a missing extra can never break an unrelated
command.

The only external binary invoked anywhere is **`git`**, from five modules.

## 6. What this means for a container

A container in which a coding agent runs needs:

```
python>=3.11, git, pip install mr-bera-harness   # PyYAML comes with it
```

and nothing else. Adding `.[postgres]` plus a database server enables the joins;
adding `.[propose]` enables proposal gating. Neither is required to use the
harness, and neither is required by CI to run the suite — the tests for those layers
skip cleanly when their extra is absent, which was verified in a venv that omits
the validator.

## 7. Honest limits of this audit

- Python ≥ 3.11 is **declared**, and the suite was run on 3.11 and 3.14 locally and
  on 3.11–3.13 in CI. No lower version is supported; `tomllib` is stdlib only from
  3.11 and the floor was raised rather than adding a dependency.
- `git` is assumed present. The harness is a git tool; a repository is the premise,
  not a dependency it can sensibly degrade without.
- Nothing here asserts capacity, cost or performance. No such figure exists.

## 8. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Recorded the runtime audit: three third-party imports, one core; no database or network required; every optional capability fails loudly. |
