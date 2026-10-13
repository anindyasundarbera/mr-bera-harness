---
type: Decision Record
id: ADR-2026-014
date: 2026-10-13
title: No PostgreSQL version is pinned, and the index stays rebuild-on-demand
status: Accepted
decision: Assert no PostgreSQL version in code or configuration, requiring the caller to supply a DSN, and keep the index rebuild-on-demand rather than a long-running service; the supported version remains a DecisionRequired for the owner.
covers: [MRB]
supersedes: []
---

# Context

`HARNESS_ARCHITECTURE.md` §10 lists two items as open: **Postgres locality**
(local-only vs shared service) and **index lifecycle** (rebuild-on-demand vs
long-running service). A third question arose in practice: **which PostgreSQL
version** the harness targets.

No authoritative document fixes any of the three. The architecture explicitly says
the design "does not presume them". So no version may be asserted: pinning one
would be inventing a capability claim, and a claim about a database version is
exactly the sort of thing `AGENTS.md` forbids supplying a plausible default for.

The current state was arrived at implicitly while building steps 1, 2 and 5. This
record makes the implicit explicit, and separates what the code has decided from
what remains the owner's.

# Decision

**Recorded as decided by the code, and therefore by this record:**

1. **No version is pinned anywhere.** `psycopg` is an optional extra with no
   version constraint on PostgreSQL itself. The DSN is supplied by the caller
   (`MRB_HARNESS_DSN` or `--dsn`); there is no default, because the harness must not
   guess a database location any more than it guesses a document path.
2. **The index is rebuild-on-demand.** There is no service, no connection pool and
   no daemon. `harness index build` and `harness index verify` connect, work and
   close. `reset` drops and recreates, which is what makes the rebuild invariant
   testable rather than aspirational.
3. **The mirror follows the same rule.** The ledger mirror resets before writing, so
   it renders the current ledger rather than accumulating.
4. **No version is claimed in CI either.** The `test` job runs a `postgres:16`
   **service container as a test fixture**, which is a statement about what the
   tests ran against, not a supported-version claim for consumers.

**Recorded as remaining the owner's:**

- **The supported PostgreSQL version range.** Any value here is a compatibility
  claim requiring validation against real installations.
- **Locality.** Local-only is the simplest and has no sync problem; a shared service
  needs auth and conflict handling. The code is compatible with either, because it
  only opens a connection it was given.
- **Whether a long-running index service is ever wanted.** Rebuild-on-demand is
  chosen now because it keeps the database provably derived; a service would need its
  own justification.

# Consequences

- **The harness claims nothing it has not validated.** A consumer on PostgreSQL 14
  or 18 is neither supported nor unsupported by the project — the project has made
  no claim, and the DSN it is given is the only fact.
- **The rebuild invariant is what protects consumers**, not a version pin: whatever
  the server version, the index must rebuild identically from git (`ADR-2026-006`).
- **A test fixture is not a support statement.** Anyone reading `postgres:16` in
  `ci.yml` should read it as "this is what CI happened to run", which the record now
  says explicitly rather than leaving to inference.
- Cost: an owner who wants a support matrix must produce one; the project is silent
  rather than wrong.

# Alternatives rejected

- **Pin a version in `pyproject.toml` or docs.** An invented compatibility claim.
- **Pin a version in CI and call it supported.** Conflates "the tests ran on this"
  with "this is supported", which is the substitution this whole record exists to
  avoid.
- **Default the DSN.** A guessed database location, and the failure mode is silent:
  the harness would connect somewhere plausible instead of saying it was not told.
- **A long-running index service.** Adds a daemon, a lifecycle and a drift surface to
  a store whose entire justification is that it can be discarded.
