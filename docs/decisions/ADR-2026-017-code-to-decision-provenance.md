---
type: Decision Record
id: ADR-2026-017
date: 2026-10-13
title: Propose linking source code to the decisions that produced it
status: Proposed
decision: Propose that a source file may declare the decision records that bind it, checked by CI so the link cannot rot, so a reader can move from a line of code to why it is that way; the mechanism is undecided and nothing is implemented.
covers: [MRB]
supersedes: []
---

# Context

The repository records decisions with their reasoning (`docs/decisions/`, fourteen
records, each with Context, Decision, Consequences and Alternatives rejected). It
records the code. **It does not record the edge between them.**

The consequence is concrete. A reader of `src/harness/propose/gate.py` can see *what*
it does, and can — if they think to look — find `ADR-2026-012` and read why the
validator is an optional extra. But nothing in the file says that record exists. The
reasoning is one search away for someone who knows to search, and invisible to
someone who does not.

That is the gap between "the repository has good documentation" and "the codebase
explains itself". The first is true today. The second is the stated purpose
(`docs/PURPOSE.md`) and is not.

Two constraints shape what a fix could be:

- **It must not be prose.** A comment saying "see ADR-012" rots silently the moment
  the ADR is superseded. Anything added must be *checkable*. This repository has
  already been bitten once by a hardcoded claim that became false without failing
  anything (`CHG-2026-016` fixed exactly that in the generated header); the same test
  applies here.
- **It must not invent provenance.** Inferring a link from filenames, commit messages
  or an embedding would produce a plausible but unverified association, which is the
  failure mode this repository exists to prevent.

# Decision

**Status: `Proposed`. Nothing here is implemented, and it must not be read as though
it were.**

The proposal is that a source file may **declare** the decisions that bind it — a
small, machine-readable declaration, not a comment — and that CI **checks** each
declared decision exists, is not superseded, and is not stale. A declaration that
points at a superseded record would fail the build rather than mislead a reader.

Deliberately undecided, and therefore not to be guessed:

1. **The declaration mechanism.** A docstring convention, a frontmatter block, a
   sidecar file, or a marker the extractor parses. Each has a different cost and a
   different failure mode.
2. **Direction.** Source → decision is the useful direction for a reader. The reverse
   (decision → affected paths) is what makes impact analysis possible, and may be a
   separate concern.
3. **Whether it is mandatory.** Requiring every file to declare a decision would
   produce ceremony; the existing decisions do not cover every file.
4. **How the dashboard or query layer surfaces it**, if at all.

A concrete risk to weigh: a declaration is a claim, and a claim that is *checked for
existence* is still not checked for *truth*. A file could declare `ADR-2026-009` and
be unrelated to it. Any implementation must state what it does and does not verify.

# Consequences of leaving it open

- **Recorded, so the purpose statement does not overclaim.** `docs/PURPOSE.md` names
  this as the principal gap, which is more honest than describing the repository as
  self-explaining.
- **Recorded, so the next session does not reinvent the framing** — or worse, claim
  the capability already exists because the documents are good.
- Cost: until it is built, moving from code to reasoning remains a search rather than
  a step. That is the current, known limitation.

# Alternatives rejected

- **A comment convention only.** Unchecked prose rots; that is the failure this record
  is trying to avoid, not a fix for it.
- **Inferring links automatically** (from filenames, commit messages, embeddings). An
  inferred association is a guess presented as provenance — the specific thing this
  repository refuses to do.
- **Declaring the capability now.** The documents are good and the mechanism exists
  for *documents*; for *code* the edge is missing. Saying otherwise would make the
  purpose statement the first stale artifact in the repository.
- **Making it mandatory in the same step.** Ceremony before value; the mechanism
  should prove useful on a few files before it is enforced on all of them.
