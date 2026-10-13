---
type: Changelog Entry
id: CHG-2026-023
date: 2026-10-13
kind: changed
title: ADR-2026-017 is superseded, and the duplicate decision index no longer restates status
summary: Settled ADR-2026-017's status by supersession -- ADR-2026-019 records supersedes [ADR-2026-017] and 017 becomes Superseded, keeping the proposal it made while removing the disagreement about a capability that now exists; and made docs/decisions/index.md a pure pointer, because it hand-synced statuses for two records only and nothing tested it.
covers: [MRB]
---

Two changes with one cause: a fact stated in more than one place, and only one of those
places generated.

## The status was genuinely `Proposed`, not an out-of-sync artifact

The owner asked whether `ADR-2026-017`'s `Proposed` status in the *Architecture Decision
Index* was a forgotten update. It was not: the index is generated, and it faithfully
reported the **source record**, which carried `status: Proposed` and a `decision:` field
saying *"the mechanism is undecided and nothing is implemented."*

So this was never an artifact-sync defect. It was an unmade decision, recorded as
decision 7 in `REMAINING_WORK.md`, which exists precisely to flag that `ADR-2026-017`
now contradicted `ADR-2026-019` — a record that *implemented* the capability 017 only
proposed.

**Resolved by supersession**, on the owner's direction:

| Record | Change |
|---|---|
| `ADR-2026-019` | `supersedes: [ADR-2026-017]` |
| `ADR-2026-017` | `status: Superseded`; its normative `decision:` and body opening now state the supersession and point at 019 |

Supersession was chosen over marking 017 `Accepted` because 017's `decision:` field says
nothing was implemented, and that was **true of 017**. Rewriting it to `Accepted` would
have made its body assert an implementation it never had; leaving its text as the
proposal and superseding it keeps every record honest.

**The digest boundary makes this safe.** `supersedes` is deliberately **not** in
`NORMATIVE_FIELDS` (`provenance/links.py`), so recording the supersession does not stale
the two files that declare a decision. Verified: `harness provenance check` still exits
`0`. Only the `status` and `decision` edits on 017 touch normative content, and no file
declares 017.

## The duplicate index, which is the real sync hazard

`docs/decisions/index.md` was **hand-maintained** and restated each record's title and —
for `ADR-2026-016` and `-017` only — its status. It was updated by hand in PR #15 because
someone remembered; `harness entries generate` does not write it, no test reads it, and
`harness doctor` does not check it. It also sat one directory away from the **generated**
`docs/DECISIONS_INDEX.md`, whose name differs by case and path — easy to edit the wrong
one.

That is a second copy of a fact with nothing checking it: the failure `CHG-2026-016`
(hardcoded header) and `CHG-2026-020` (stale README) were both raised for.

It is now a **pure pointer**. It names the generated index, says which file is
authoritative, and repeats no list and no status — so there is nothing left in it to
drift. This is the owner's own principle applied: *point at the artifact rather than
restate it verbatim*, so an agent consumes one authority instead of several copies.

`REMAINING_WORK.md` decision 7 is closed and its change history records v2.3.

## A live reproduction of decision 8, while resolving the merge

Resolving this PR's conflict against `main` produced a failure worth recording, because
the cause was proven rather than inferred. With the merge resolved but **not yet
committed**, `tests/test_dashboard.py::test_guards_on_a_feature_branch_pass` failed —
the exact environment dependency §5.2 describes. The evidence:

```
merge-base HEAD origin/main = bcccc14…   # the pre-merge tip, one commit behind
→ guards reported `fail`; the test failed
(create the merge commit)
merge-base HEAD origin/main = 4740647…   # now the tip
→ the same test passed, unchanged
```

**Nothing in the branch or the test changed between the two runs — only the checkout's
position did.** That is decision 8's second consequence demonstrated on demand instead
of described, and §5.2 now records the reproduction. The defect itself is still unfixed:
it is a semantics question about the `branch` argument's contract, and it remains the
owner's to decide.

**Tests:** 624 without a database; coverage 82.2%. `harness doctor` clean (44 entries,
0 problems), `harness provenance check` exit 0, `refresh_handoff.py --check` exit 0.
