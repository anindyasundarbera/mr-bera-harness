---
type: Decision Record
id: ADR-2026-013
date: 2026-10-13
title: Session records live in git notes, and the ledger never executes
status: Accepted
decision: Store session records as append-only NDJSON in a configurable git notes ref so they survive a repository copy, keep the Postgres mirror strictly derived and rebuildable from the notes, and keep the ledger free of any path that executes a recorded proposal.
covers: [MRB]
supersedes: []
---

# Context

Build-order step 5 records "prompt, proposal, verdict, effect" for a session. Two
questions decided the shape.

**Where does the record live?** `HARNESS_ARCHITECTURE.md` §9 names "`git notes` +
Postgres", and §5.3 gives the reasoning: git is already an append-only,
content-addressed, cryptographically ordered event log with a distributed transport,
and `git notes` extends it with metadata that does not rewrite history. §10 lists
the metadata store as an open decision and notes that "`git notes` survives a repo
copy; Postgres alone does not". So §9's naming settles it, and the mirror is a
derived index by the same argument as step 1.

**Does the ledger execute?** §9 lists "effect" as a recorded field. The temptation
is for the ledger to *perform* the effect and record it, which would make it the
second executor `ADR-2026-005` rules out.

# Decision

1. **Records are append-only NDJSON in `refs/notes/harness`**, configurable with
   `--ref`. One record is one line, because `git notes append` separates messages
   with a blank line and a multi-line document would be ambiguous to split.
2. **The prompt is stored by reference** — its step-3 fingerprint, budget, unit and
   entry count — never as text. The fingerprint already binds the bytes and the
   manifest, and duplicating the prompt would create a second copy to keep in step
   with the compiler.
3. **The ledger executes nothing.** It records what the caller reports. The default
   effect is `not-observed`, which is the truth about a recorder that was not told.
   `applied`, `failed` and `none` are caller reports, not observations.
4. **The Postgres mirror is derived and provably so.** Written from the notes and
   nothing else; resets first so it is a rendering of the current ledger rather than
   an accumulation; and each row stores both the queryable columns and the whole
   record, so the rebuild-identity comparison is exact rather than partial.
5. **Transport is documented and printed, never performed.** A `git notes` ref is
   not carried by a plain clone or fetch — measured, not assumed. `harness ledger
   transport` prints the exact push and fetch commands.

# Consequences

- **A record survives a repository copy**, which is the property Postgres alone
  cannot provide. Copying the repository carries the note object with it.
- **The mirror cannot become authoritative.** It is rebuilt from the notes on every
  write, so a record deleted from the notes disappears from the mirror rather than
  lingering as a fact git does not hold.
- **The propose/dispose split holds across a whole session**, not only at the moment
  of a proposal. Because there is no execution path in the ledger, a `permitted`
  verdict recorded today cannot be applied by reading the ledger tomorrow.
- **The transport limitation is explicit.** This is a real cost of choosing notes:
  collaborators do not see the ledger until the ref is fetched. It is documented in
  the design note and printed by the CLI, because a ledger believed to be complete
  and silently missing remote entries would be worse than no ledger.
- Cost: an append is a git write, so a ledger entry changes the notes ref and
  therefore the repository's object store, though never the working tree — asserted
  by a test, since a ledger that dirtied the tree would make every subsequent run
  report a dirty tree.
- Cost: the mirror needs a schema (`LEDGER_SCHEMA_VERSION`) and a record version
  (`RECORD_VERSION`), both of which invalidate older data when changed. That is the
  price of a readable contract.

# Alternatives rejected

- **Postgres only.** §10 records that it does not survive a repository copy, which
  is the whole point of the memory being durable.
- **In-tree files under the bundle.** The index would treat each record as a
  concept, and every session would dirty the working tree.
- **One note per record, under a ref per record.** `git notes` attaches one note per
  object; multiple records per commit need either one composite note (chosen) or a
  ref per record, which multiplies refs and makes the ledger hard to enumerate.
- **The ledger applying the effect it records.** That is a second executor, and it
  makes a recorded verdict a capability rather than a decision.
- **Inventing an effect when the caller did not report one.** The field exists to
  say what is known; `not-observed` is what is known.
- **Reimplementing note storage as a file format.** `git notes` already provides
  conflict-resolution strategies for merging notes, which a bespoke format would
  have to reinvent.
