---
id: HARNESS-LEDGER-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, PROMPT_COMPILER.md, PROPOSAL_GATES.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Session ledger

> ID: HARNESS-LEDGER-001
>
> Status: **Implemented** — build-order step 5 of `HARNESS_ARCHITECTURE.md` §9.
>
> Authority: a design document. The storage and no-execution decisions are
> `ADR-2026-013`.

---

## 1. What this is

Build-order step 5: *`git notes` + Postgres; prompt, proposal, verdict, effect.*

A session leaves a record — what prompt was sent, what was proposed, what the gates
decided, and what the caller reports happened — attached to the commit it concerns.
The record lives in git, so it survives a repository copy. A Postgres mirror is
optional and derived.

```bash
harness ledger append --work-id MRB-M06-S01 \
    --prompt-fingerprint <sha256> --budget 4000 --unit word \
    --proposal p.json --gate --effect applied
harness ledger show      # records for a commit
harness ledger list      # every record
harness ledger verify    # integrity, and the ledger digest
harness ledger mirror    # write the optional Postgres mirror
harness ledger transport # the commands that carry the notes ref
```

## 2. Why `git notes`, and the limitation that comes with it

§5.3 gives the reasoning: git is already an append-only, content-addressed,
cryptographically ordered event log with a distributed transport, and `git notes`
extends it with metadata that does not rewrite history. A record attached to a
commit therefore **survives a repository copy** — the property §10 names as the
reason to prefer notes over Postgres alone.

**A `git notes` ref is not fetched by a plain `git clone` or `git fetch.`** This was
measured, not assumed:

```
$ git clone … new-copy && cd new-copy && git notes --ref=harness show HEAD
error: no note found for object …
```

The records travel only when the ref is transported explicitly, which
`harness ledger transport` prints:

```
git push  origin refs/notes/harness
git fetch origin refs/notes/harness:refs/notes/harness
```

This matters more than a footnote. A ledger that appeared to work locally and
silently did not travel would be worse than no ledger, because a reader would
believe a history they cannot see. The CLI prints the commands rather than
executing them: pushing is a separate, authorised action, and a library that
pushed on its own would be a network side effect nobody asked for.

## 3. The prompt is recorded by reference

Step 3's fingerprint covers the prompt bytes **and** the manifest of what is in it,
so a recorded fingerprint proves what was sent without storing the prompt twice. A
ledger that duplicated the text would be a second copy to keep in step with the
compiler — exactly the drift §5 exists to prevent.

`PromptRef` therefore carries `fingerprint`, `budget`, `unit` and `entry_count`.
The budget is recorded because it bounds admissibility and a reader needs it to
interpret the fingerprint; it is *not* part of the fingerprint, for the reason
`ADR-2026-010` gives.

## 4. The ledger records; it does not execute

`HARNESS_ARCHITECTURE.md` §9 lists "effect" as one of the four things a record
carries. The ledger has no executor, so it **cannot observe** an effect itself.
It records what the caller reports, and the default is `not-observed` — the
truthful value for a recorder that was not told.

| `effect` | Meaning |
|---|---|
| `not-observed` | default; the caller did not report, and the ledger did not see |
| `applied` | the caller reports the permitted proposal was carried out |
| `failed` | the caller reports it was attempted and failed |
| `none` | permitted, and deliberately not acted on |

An invented effect would be the ledger claiming knowledge it does not have. A test
asserts no path from a record's contents to execution: every `subprocess` call is a
literal git command (so nothing built from a record reaches a shell), no
write/delete call exists outside git's own notes, and appending a record leaves the
working tree byte-identical.

## 5. Append-only, and additive by construction

A record is one NDJSON line, because `git notes append` separates messages with a
blank line and a multi-line JSON document would be ambiguous to split back apart.
`git notes append` creates the note when none exists, so first-record and
tenth-record take the same path.

A malformed line is an **error, never a skipped entry**: a ledger that silently
dropped an entry would be indistinguishable from one where the event never
happened.

## 6. The Postgres mirror is derived, and provably so

The mirror exists for the joins §5.2 says git cannot do — *"which sessions touched
this work item?"* is a query, not a log read. It is written **from the notes and
nothing else**, and the same invariant as step 1 applies: drop it, rebuild from the
notes, require identical digests.

Two design details make that provable rather than aspirational:

- Each row stores the queryable columns **and** the whole record as canonical JSON.
  Storing only the columns would make the mirror unable to be proved identical to
  its source — the invariant would be unprovable by construction, which is worse
  than not having one.
- `write_mirror` **resets first**, so the mirror is a rendering of the current
  ledger rather than an accumulation. A record removed from the notes disappears
  from the mirror too; otherwise the mirror would slowly become the authority it is
  supposed to be derived from.

A repository with no database still has a complete ledger. The notes are the record.

## 7. Exit codes

| Code | Meaning |
|---|---|
| `0` | done |
| `1` | an integrity problem: an unreadable record, or a mirror that differs |
| `3` | the mirror was requested and Postgres is unreachable |
| `4` | usage error |

## 8. Deliberately not here

| Not built | Why |
|---|---|
| Executing a recorded proposal | the ledger records; the executor is a separate concern |
| Auto-pushing the notes ref | a network side effect nobody asked for |
| Storing the prompt text | the fingerprint already binds it (`ADR-2026-010`) |
| Treating the mirror as authoritative | it is derived, and rebuildable (`§5`) |
| A notes ref that a consumer cannot change | `--ref` is configurable; the default is `harness` |

## 9. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Build-order step 5 implemented: versioned record, append-only notes, derived Postgres mirror, transport documented. |
