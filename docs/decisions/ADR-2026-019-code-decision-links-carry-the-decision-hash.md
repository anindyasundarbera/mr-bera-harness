---
type: Decision Record
id: ADR-2026-019
date: 2026-10-13
title: A code-to-decision link carries the decision's anchor hash, and is declared never inferred
status: Accepted
decision: Require every code-to-decision declaration to carry the decision's anchor digest over its normative content, so a revised decision flags every implementing file as stale; compute the digest over normative fields and the opening prose only; and keep the link declared by a person and merely verified by the tool.
covers: [MRB]
supersedes: []
---

# Context

`ADR-2026-017` recorded the gap and proposed that a source file may declare the
decisions binding it, checked by CI. It deliberately left the mechanism undecided.
Implementing it forced four choices, each with a failure mode.

**1. What makes the link checkable?** A comment saying *"see ADR-012"* rots: the
decision can be revised, superseded or replaced, and the comment still reads as
current. A check for mere *existence* catches only the crudest case — a decision that
was deleted.

**2. If the link carries a hash, what does the hash cover?** Hashing the whole
document means a change to the change-history table, or a date, makes every implementing
file report stale. A digest that moves for reasons that do not invalidate anything
**cries wolf until nobody reads it** — and then the real finding is ignored too.

**3. Where does the declaration live?** This was learned the hard way. An automated
placer inserted the marker after the first line ending in a triple quote, which in
`index/schema.py` was **inside the SQL DDL string**. The SQL stopped being valid, and
the file still parsed as Python, so the damage was invisible until a test connected to
a database. A second insertion landed inside a dataclass body.

**4. Who authors a link?** If a tool infers it — from filenames, commit messages, or an
embedding — the result is a guess presented as provenance, which is the specific thing
this project refuses to do.

# Decision

**1. The declaration carries the decision's anchor digest.**

```python
# harness:decision ADR-2026-009 sha256:a6d5f77e7cfb
```

A revised decision changes the digest, so every file that declared the old one is
reported **stale** with both hashes and an actionable message. That is what turns the
link from prose into a check.

**2. The digest covers normative content only** — `id`, `title`, `status`, `decision`,
`covers`, and the first prose paragraph. It excludes `date`, `supersedes`, the
change-history table and later narrative. A test asserts **both** sides of that
boundary, because a digest that is too eager is as useless as one that is too lazy.

**3. A declaration must be a module-level comment introduced by a comment marker at
line start.** Two consequences, both deliberate:

- prose *about* the format is not a declaration. Without this, this package's own
  `links.py` and `__init__.py`, which document the marker, were parsed as declaring
  decisions — a false positive, and a checker that reports false positives gets
  ignored.
- a marker inside a string literal or a class body is **not** a declaration, and a test
  inspects the AST of every source file to prove none exists. This is the guard for the
  DDL corruption that actually happened.

**4. The link is declared by a person and verified by the tool.** Nothing is inferred,
and the module imports nothing that could reach a model, a network or a shell — a test
asserts that from the imports.

**5. Two findings, never collapsed:** `broken` (the decision does not exist) and
`stale` (it exists and changed). They call for different actions.

**6. The links are also written to the derived index**, so *"which code was written
against a decision that has since changed?"* is a join rather than a file-by-file
check. Derived and reset on each write, like every other store here.

# Consequences

- **A decision cannot change quietly out from under its code.** Editing one flags
  every implementing file, with both hashes, in one command.
- **Noise is bounded by design.** Date and history changes do not trigger the alarm, so
  the alarm keeps its meaning.
- **The failure modes are named, not implied.** `broken` and `stale` say different
  things; `unlinked` is reported but not an error, because requiring a declaration on
  every file produces ceremony rather than provenance.
- **What it does not verify is stated.** A file can declare a decision unrelated to it:
  the check verifies the decision exists and has not moved, **not that the code
  implements it**. An undeclared change remains invisible. Both are in the design note
  rather than left to inference.
- Cost: a person must write the declaration, and update it when a decision is
  deliberately revised. That is the price of a checked link; the alternative is a
  comment nobody can trust.
- Cost: the digest boundary is a judgement — normative fields plus the opening prose —
  and it will occasionally be wrong in one direction or the other. It is recorded,
  tested on both sides, and changeable by amending this record.

# Alternatives rejected

- **Existence-only checking.** Catches a deleted decision and nothing else; a revised
  decision would silently invalidate its implementations.
- **Hashing the whole document.** Every date and history edit would report false
  stales; the alarm becomes noise and is then ignored.
- **A free-text comment convention.** Unparseable, unverifiable, and it rots — the
  failure this record exists to fix.
- **Inferring the link.** A guess presented as provenance. Rejected in `ADR-2026-017`
  and rejected again here.
- **A declaration inside a docstring.** Reads naturally, but the marker then sits in a
  string literal where the DDL case proved damage can hide, and prose about the format
  becomes indistinguishable from a declaration.
- **Requiring every file to declare.** Ceremony before value; a decision can be about
  process, and not every file has one behind it.
