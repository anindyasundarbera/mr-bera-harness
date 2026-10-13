---
type: Changelog Entry
id: CHG-2026-019
date: 2026-10-13
kind: added
title: Code provenance — every file can declare the decision that produced it
summary: Closed the gap docs/PURPOSE.md named, by letting a source file declare the decisions binding it with the decision's anchor hash, so a revised decision flags every implementing file as stale; the links are checked in CI and written to the derived index for joins.
covers: [MRB]
---

Closes the principal gap `docs/PURPOSE.md` §4 named in its own honest list: *"code has
no provenance link to the decisions that produced it."* Implements `ADR-2026-017`;
the mechanism is `ADR-2026-019`.

```bash
harness provenance marker ADR-2026-009     # the line to paste
harness provenance check                   # verify every declaration
harness provenance map                     # what declares each decision
harness provenance index                   # the same links, in the derived index
```

## The hash is what makes it a check rather than a comment

A declaration carries the decision's **anchor digest**:

```python
# harness:decision ADR-2026-009 sha256:a6d5f77e7cfb
```

Edit the decision and the hash stops matching, so every file that implements it is
reported stale — with both hashes and an actionable message:

```
STALE (1) — the decision changed after this was written
  src/harness/index/schema.py:19  `ADR-2026-009` has changed since this file declared it
  (declared sha256:a6d5f77e7cfb, now sha256:6958e364bfac)
```

**Demonstrated, not asserted:** editing `ADR-2026-009` in the real repository flipped
`index/schema.py` from verified to stale in one command. Restoring the decision
returned it to green.

## The digest boundary is deliberate

Covered: `id`, `title`, `status`, `decision`, `covers`, and the **first prose
paragraph**. Excluded: `date`, `supersedes`, the change-history table, later narrative.
A digest that moved for a date would cry wolf until nobody read it — and then the real
finding would be ignored too. Tests assert **both** directions of that boundary.

## Nothing is inferred

A person writes the declaration; the tool only verifies it. No model, no network, no
shell — asserted from the module's own imports by a test. An inferred link would be a
guess presented as provenance, which is precisely what this project refuses to do.

`broken` (the decision does not exist) and `stale` (it exists and changed) are reported
separately, because they call for different actions. `unlinked` is reported only with
`--require-all`: requiring a declaration on every file produces ceremony, not
provenance.

## In the codebase and in the index

`harness provenance index` writes `decisions` and `code_links`, so *"which code was
written against a decision that has since changed?"* is a **join** across the whole
repository rather than a file-by-file check. Derived and reset on each write, like
every other store here — a declaration removed from a file disappears from the index.

## Two bugs found while building

1. **A false positive, immediately.** The package's own docstrings *document* the
   marker, so the scanner parsed its own documentation as declarations. Fixed by
   requiring a comment introducer at line start. A checker that reports false positives
   gets ignored, and then the real finding is ignored too.
2. **A declaration placed inside a SQL string, by an automated placer.** It inserted
   after the first line ending in a triple quote — which in `index/schema.py` was
   **inside the DDL**. The SQL stopped being valid while the file still parsed as
   Python, so the damage was invisible until a test connected to a database. A second
   insertion landed inside a dataclass body. Both repaired, and a test now walks the
   AST of every source file to prove no declaration sits inside a string literal or a
   class body.

## What it does not verify

A file can declare a decision **unrelated** to it. The check verifies the decision
exists and has not moved — **not** that the code implements it. An undeclared change
remains invisible. Stated in the design note rather than left to inference.

**Tests:** 600 without a database; **676 with a live PostgreSQL**, coverage 91.4%
(`store.py` 100%, `links.py` 95%). Lint, format, `mypy --strict`, `harness doctor`,
`harness guards` and `harness ci` all clean.
