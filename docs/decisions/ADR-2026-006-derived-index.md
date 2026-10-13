---
type: Decision Record
id: ADR-2026-006
date: 2026-10-13
title: The document index is derived from git and must rebuild identically
status: Accepted
decision: Store the extracted document model in PostgreSQL as a strictly derived index that can be destroyed and rebuilt from committed git bytes, and prove rebuild-identity with a digest test rather than by convention.
covers: [MRB]
supersedes: []
---

# Context

`HARNESS_ARCHITECTURE.md` §5 gives git the role of source of truth and PostgreSQL
the role of derived, rebuildable index, and §5.1 states the invariant that keeps
them honest. Build-order step 1 had to implement that division, and the failure
mode is specific and well known: a derived store silently drifts from the source
it was derived from until it is, in practice, authoritative.

Two sources of truth always drift. The question is not whether to have an index —
joins and aggregates need one — but what stops it from becoming a second author.

# Decision

The index is **strictly derived**. Extraction reads **committed git bytes** and
produces a normalized model; the database stores a rendering of that model and
nothing else. There is no default DSN, and the only writer writes a model that
came from git.

The invariant is enforced as a test, not by convention:

1. drop the index tables;
2. rebuild from git;
3. require the two models' digests to be identical **and** compare them
   table-by-table.

The digest is SHA-256 over a canonical JSON rendering, and `read_model`
reconstructs a model from the rows alone — never from the filesystem or git. That
is what makes the comparison capable of failing: a fact that did not round-trip
changes the digest.

The test also asserts the model is non-empty and that a committed change *breaks*
the equality. Without those, the invariant could pass while indexing nothing.

# Consequences

- **PostgreSQL may be destroyed at any time** without loss of a fact. Rebuild is
  `harness index build`.
- **Uncommitted work is invisible to the index**, by construction — `git archive`
  is materialized rather than the working tree walked. An index therefore never
  encodes a fact git does not hold.
- **The index is optional.** `psycopg` remains an extra and the index tests skip
  gracefully without a DSN, so the derived layer cannot break CI.
- Cost: extraction re-reads from git on each build rather than incrementally.
  That is deliberate — an incremental path is where drift is reintroduced.
- Cost: the model's shape is a versioned artifact (`MODEL_VERSION`,
  `INDEX_SCHEMA_VERSION`); changing it invalidates existing indexes rather than
  silently reinterpreting them.

# Alternatives rejected

- **Incremental, change-driven indexing.** Faster, but it makes the database a
  participant in deciding what is true, which is the drift this decision exists
  to prevent.
- **A database-version pin in code.** Rejected: no authoritative document fixes a
  PostgreSQL version for the index. A test host may be anything; the code asserts
  none. Recorded as `DecisionRequired` rather than invented.
- **Indexing the working tree as well as commits.** Rejected: it would let an
  uncommitted edit become a queryable fact, and the index would disagree with git
  by design.
