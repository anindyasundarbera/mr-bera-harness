---
id: HARNESS-PROVENANCE-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, PURPOSE.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Code provenance

> ID: HARNESS-PROVENANCE-001
>
> Status: **Implemented** — the gap `docs/PURPOSE.md` named. The decision is
> `ADR-2026-017`; the mechanism-specific choices are `ADR-2026-019`.

---

## 1. What this closes

`docs/PURPOSE.md` §4 named the principal gap in its own honest list:

> **Code has no provenance link to the decisions that produced it.** A file cannot
> say *"this exists because of `ADR-2026-009`"*. The reasoning is recorded and the
> code is recorded, but the edge between them is not.

The edge now exists, and — the part that matters — it is **checked**.

```bash
harness provenance marker ADR-2026-009     # the line to paste into a file
harness provenance check                   # verify every declaration
harness provenance map                     # which files declare each decision
harness provenance index                   # the same links, in the optional index
```

## 2. The hash is the mechanism

A comment saying *"see ADR-012"* rots silently the moment the decision is revised.
So the declaration carries the decision's **anchor digest**:

```python
# harness:decision ADR-2026-009 sha256:a6d5f77e7cfb
```

Edit the decision and the hash no longer matches, so **every file that implements it
is reported stale**:

```
$ harness provenance check
decisions   : 18
declarations: 2
verified    : 1

STALE (1) — the decision changed after this was written
  src/harness/index/schema.py:19  `ADR-2026-009` has changed since this file declared it
  (declared sha256:a6d5f77e7cfb, now sha256:6958e364bfac) — re-read the decision and
  either update the declaration or revert the change
exit 1
```

That is the whole feature: a decision cannot change quietly out from under the code
that implements it.

## 3. What the digest covers, and what it deliberately does not

The anchor digest covers a decision's **normative** content:

| Included | Why |
|---|---|
| `id`, `title`, `status`, `decision` | these state what is required |
| `covers` | this states what the decision is *about* |
| the **first prose paragraph** | where a record states its decision in a sentence |

| Excluded | Why |
|---|---|
| `date` | a date does not change what is required |
| `supersedes` | records history, not requirement |
| later prose, the change-history table | narrative below the opening statement |

A digest that moved for a date would cry wolf until nobody read it, and then the real
finding would be ignored too. A test asserts each side of that boundary.

## 4. Nothing is inferred

A tool must not **guess** which decision produced a line of code — an inferred
association is a guess presented as provenance, which is the failure mode this whole
project exists to prevent. So:

- a **person** writes the declaration;
- the check only **verifies** it;
- no model, no network, no shell: asserted from the module's own imports by a test.

## 5. Two findings, deliberately separated

| Finding | Meaning | Action |
|---|---|---|
| **broken** | the decision does not exist | the declaration names nothing |
| **stale** | the decision exists but its anchor changed | re-read and update, or revert |

They are reported separately because they call for different actions. Collapsing them
would hide which one is needed.

**`unlinked`** — a source file with no declaration — is reported only with
`--require-all`. Requiring a link on every file produces ceremony, not provenance;
the useful direction is the one this enables, which is answering *what implements this
decision?*

## 6. The links in the index, so they can be joined

The owner's requirement was that the link live **in the codebase and in the database**,
with the hash connecting the files. `harness provenance index` writes both:

| Table | Holds |
|---|---|
| `decisions` | each decision, its status, and its current anchor digest |
| `code_links` | each declaration: path, line, decision id, declared digest, whether it matches |

That makes the question a **join** rather than a file-by-file check:

```
$ # which code was written against a decision that has since changed?
       STALE  src/harness/index/schema.py:19  ADR-2026-009
              declared a6d5f77e7cfb  now 4517fa8014e0
```

Like every store here it is **derived** — written from the declarations and the
decision records, reset before each write, and rebuildable. A declaration removed from
a file disappears from the index; the index is never where a link is authored.

## 7. What it does not verify

Stated plainly, because a claim checked for **existence** is still not checked for
**truth**:

- A file may declare a decision that is **unrelated** to it. The check verifies the
  decision exists and has not changed; it cannot verify that the code actually
  implements it.
- A decision may be declared by **no** file. That is reported, not an error: some
  decisions are about process and produce no code.
- An **undeclared** change is invisible. This tool makes a declared link checkable; it
  does not compel declaration.

## 8. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Implemented: declaration marker, anchor digest, check with broken/stale findings, reverse index, and the derived index tables. |
