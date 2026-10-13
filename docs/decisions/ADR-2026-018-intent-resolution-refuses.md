---
type: Decision Record
id: ADR-2026-018
date: 2026-10-13
title: Instruction resolution refuses rather than guesses, and calls no model
status: Accepted
decision: Implement build-order step 6 as a deterministic, fallible resolver that extracts identifiers the instruction names, scores the decomposition lexically, and refuses with a clarification request whenever the answer is not unique — never calling a model and never picking a winner on ambiguity.
covers: [MRB]
supersedes: []
---

# Context

Step 6 is the only build-order step `HARNESS_ARCHITECTURE.md` rates **not
deterministic** (`No`), least provable, and — §9 — one the design **must not depend
on**:

> a human who writes the task ID directly bypasses step 6 entirely and loses nothing

§8 is equally specific about what can honestly be built: *intent classification is
fuzzy*, so the answer is *"deterministic prompt **assembly**; intent resolution is
explicit and fallible, with a human-clarification fallback."*

Two temptations had to be refused.

**1. Classify intent.** The obvious implementation asks a model, or builds a
classifier, and it would work often enough to look successful. But it would make the
step's output probabilistic while the rest of the pipeline — prompt, fingerprint,
verdict, ledger record — is deterministic, and it would put a model **inside the
extraction path**, which §4 exists to prevent: *"if an LLM sits in the runtime
extraction path, the system is probabilistic wearing a deterministic label."*

**2. Pick the best guess.** Given several candidates, choosing the highest-scoring one
is a small step that looks like helpfulness. But §9 makes a wrong guess strictly
worse than no answer here: a mis-resolved instruction compiles a prompt bound to the
**wrong work item** and presents it as authoritative — and because the rest of the
pipeline is deterministic, nothing downstream would catch it.

# Decision

1. **No model, no network, no shell.** Resolution is lexical and deterministic. The
   module imports nothing that could reach out, asserted by a test.
2. **Three things only:** extract identifiers the instruction *already contains*
   (per the configured grammar — exact, not inferred); score every identifier the
   decomposition declares; refuse when the answer is not unique.
3. **Refusal is the feature.** Two or more identifiers named, a tie, a close
   runner-up (within 80% of the leader), or nothing above the cut → a clarification
   request with an exit code, and **no winner chosen**.
4. **Three-valued outcome** — `resolved` / `ambiguous` / `unresolved` — and `chosen`
   is `None` unless resolved. The same discipline as the dashboard's status and the
   gate verdicts.
5. **Concepts widen the reach.** Scoring uses the titles of the concepts that *cover*
   an identifier, not only the identifier's own title, so a phrase that appears in no
   identifier can still reach the right one — verified in a consumer, where *"the
   ledger writer"* resolved to `EPIC-P01-S01`.
6. **An explicit `--work-id` bypasses resolution entirely**, because the architecture
   says so: a human naming the work item loses nothing. The reason string says
   *"nothing was inferred"* rather than pretending a resolution happened.
7. **Resolution is not a gate.** A resolved work item still meets the compiler's
   refusals, so a blocked item still exits 3.

# Consequences

- **The step cannot silently corrupt the pipeline.** Its failure mode is a question,
  not a wrong answer, which is what makes it safe to have at all.
- **The pipeline stays deterministic end to end.** Fingerprint, verdict and ledger
  record remain reproducible, because resolution either yields an identifier the
  person wrote or asks.
- **Explainability is designed in.** The scorer is Jaccard overlap over content words
  — chosen because a person being asked to clarify must be able to see *why*. A
  cleverer scorer would be harder to justify in the question it asks.
- **A paraphrase with no shared vocabulary is `unresolved`.** That is an honest
  limitation, not a bug: nothing here claims semantic understanding.
- Cost: an operator must occasionally name the work item. Given §9 states that loses
  nothing, the cost is correct rather than regrettable.
- Cost: the two grammar bugs found in this step (an anchored pattern cannot scan;
  concatenating level groups makes every level mandatory) show the resolver inherits
  the identifier grammar's subtleties. Both are now pinned by tests.

# Alternatives rejected

- **Ask a model to classify the intent.** Puts a model in the extraction path (§4),
  makes the step non-reproducible, and contradicts §8's stated resolution.
- **Pick the highest-scoring candidate.** A wrong pick is worse than no answer (§9),
  and it would be invisible downstream because everything after it is deterministic.
- **Embedding similarity.** Non-deterministic across model versions, and it would make
  a recorded resolution irreproducible — the property the rest of the pipeline is
  built to have.
- **Require an explicit work ID and skip resolution entirely.** §9 permits it and this
  module would then be unnecessary. Kept as the *bypass* (`--work-id`) rather than the
  only route, because resolution is useful when it is right and harmless when it
  refuses.
- **A boolean "did it resolve?".** `ambiguous` and `unresolved` mean different things
  to the person being asked, and a boolean would collapse them.
