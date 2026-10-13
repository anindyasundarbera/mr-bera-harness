---
type: Changelog Entry
id: CHG-2026-005
date: 2026-10-13
kind: added
title: Extraction and a derived index that rebuilds identically from git
summary: Implemented build-order step 1 — committed git bytes are extracted with the tested OKF reader into a normalized model with a stable digest, loaded into PostgreSQL as a derived index, and proven rebuild-identical by dropping the database and rebuilding from git.
covers: [MRB]
---

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

- `psycopg` stays an optional extra, the index tests skip cleanly without a DSN,
  and no PostgreSQL version is asserted — no authoritative document fixes one.
- Registry files are read from `[registries.*]` in `harness.toml`; the harness
  never guesses which documents are registries.
- Paths resolve from the invoking directory. Resolving a caller's context from
  the library's own location is a defect this repository has hit repeatedly.

**Tests:** 329 passing (15 skipped without a DSN); 344 passing against a live
PostgreSQL, coverage 87.9% against an 80% floor. Lint, format, `mypy --strict`,
`harness doctor` and `harness ci` all clean.
