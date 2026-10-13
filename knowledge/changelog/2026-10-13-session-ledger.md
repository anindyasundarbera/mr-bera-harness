---
type: Changelog Entry
id: CHG-2026-014
date: 2026-10-13
kind: added
title: Session ledger — what was sent, proposed, decided and observed
summary: Implemented build-order step 5, recording each session as an append-only entry in git notes bound to its commit, with an optional Postgres mirror derived from the notes and proved rebuild-identical.
covers: [MRB]
---

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
