# Purpose

> Why this repository exists, what it is for, and — stated plainly — how much of
> that is already true.

---

## 1. The problem

A running system tells you what it is doing. A codebase does not.

Ask a live service for its state and it answers: what is configured, what is
healthy, what changed, what is blocked. Ask a repository the same questions and you
get a directory of files that were accurate the day they were written. The
knowledge that produced the code — *why this, why not that, what was ruled out* —
lives in people's heads, in a chat thread, or in a document nobody re-read.

So the usual answer is: **write documentation, and watch it go stale.** A new
developer, or a new agent, reads a description of a system that no longer matches
the system. Worse, they cannot tell the two apart, because prose has no exit code.

## 2. The intention

**Treat the repository as a live system rather than a folder of documents.**

Everything a developer would otherwise have to reconstruct should be an artifact
that a programme can read, a test can check, and an agent can be handed verbatim:

| Question | Where the answer lives |
|---|---|
| What is this thing for? | the decision records' *Context* and *Decision* |
| Why was it done this way? | the *Alternatives rejected* in the same record |
| Which documents bind my work item? | `harness context` — computed, not curated |
| Is this value decided, or must I stop? | a non-zero exit code naming the blocker |
| What did previous sessions do? | the session ledger in `git notes` |
| Is the documentation still true? | CI — conformance, routing and entry checks |
| What is unhealthy right now? | `harness dashboard run` |

The distinguishing property is not that the answers exist. It is that **they are
computed and refutable**. A document that disagrees with the repository fails
`harness doctor`. A decision that lacks its reasoning fails the entry schema. An
undecided value stops work with an exit code instead of being filled in with
something plausible.

## 3. Why "living" and not "documented"

Documentation is written *about* a system and drifts. These artifacts are written
*into* it and are checked:

- **Frontmatter is routing, not prose.** It says which work items a document binds,
  so context is a set intersection rather than a judgement call.
- **Decisions carry their reasoning in a fixed shape** — Context, Decision,
  Consequences, Alternatives rejected. A reader gets the *why* in the same place,
  every time, without interviewing anyone.
- **Generated files say they are generated** and are regenerated from entries, so
  the index cannot disagree with what it indexes.
- **CI is the oracle.** If the documentation and the repository diverge, the
  pipeline says so — which is what makes the claim testable rather than aspirational.

## 4. How much of this is true today

Stated plainly, because a purpose statement that overclaims is the exact failure it
is meant to fix.

**Implemented and tested:**

- Decision records with reasoning, validated by schema and indexed automatically.
- `harness context` — resolves the documents binding a work item, and **stops** with
  a named blocker rather than allowing a guess.
- The extract/index/query layer, so lookups are SQL rather than file-reading.
- The prompt compiler — a work item and a budget become a deterministic prompt whose
  SHA-256 fingerprint binds exactly what was sent.
- Proposal gating — six rules from the architecture, enforced, executing nothing.
- The session ledger — what was proposed, decided and observed, in `git notes`, so
  it survives a repository copy.
- The dashboard — health and history, as one self-contained file.
- Runtime dependencies audited: Python ≥ 3.11, `git`, and PyYAML. No database, no
  server, no network.

**Not yet true — and the gap that matters most:**

- **Code has no provenance link to the decisions that produced it.** A file cannot
  say *"this exists because of `ADR-2026-009`"*. The reasoning is recorded and the
  code is recorded, but the edge between them is not. That edge is what would let a
  reader move from a line of code to why it is that way — and it is the next thing
  that would make "the codebase is alive" more than a description of its documents.
- **Instruction → prompt (build-order step 6) is not built**, and the architecture
  says nothing may depend on it: a human typing a work item ID loses nothing.
- **`harness ci` is not project-agnostic** in a consuming repository: it runs the
  harness's own pipeline rather than the consumer's (`ADR-2026-016`, `Proposed`). Recorded as a proposed defect.

## 5. What the repository is not claiming

- It does not claim the model is deterministic. **The LLM proposes; the harness
  disposes** (`ADR-2026-005`) — the model executes nothing.
- It does not validate chain-of-thought. That is unobservable and has no ground
  truth; output and effect are validated instead (`§1.1`).
- It does not claim to replace tests, review or human approval. Gating a proposal is
  not the same as verifying its effect.
- No capacity, cost or performance figure is asserted anywhere. None has been
  measured.

## 6. The test of whether this is working

A reader — human or agent — should be able to arrive at an unfamiliar repository and
answer, **without asking anyone and without guessing**:

1. what this is for,
2. why it is shaped the way it is,
3. which documents bind their change,
4. what is blocked and must not be decided by them,
5. what previous sessions did and what was observed.

If an answer requires a conversation, the artifact is missing. That is the standard
this repository is held to.

## 7. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Stated the purpose, and separated what is implemented from what is aimed at. |
