---
type: Decision Record
id: ADR-2026-010
date: 2026-10-13
title: Prompt budgets are exact word counts, and the budget is caller-supplied
status: Accepted
decision: Express a prompt budget as an exact, provider-independent word count with no default value, and refuse rather than truncate when a selection does not fit; adopting a model's tokenizer is left as a recorded DecisionRequired.
covers: [MRB]
supersedes: []
---

# Context

Build-order step 3 compiles a bounded prompt. `HARNESS_ARCHITECTURE.md` §3 names
"token budget" and §9 names "task ID + selection + budget", but **no authoritative
document fixes either a unit or a value**:

- no budget value appears anywhere, so any default would be an invented threshold;
- the unit is called "token", but a token depends on the *model's tokenizer* — so
  a count expressed in tokens means something different for every provider, and
  a fingerprint recorded under one tokenizer is incomparable with one recorded
  under another.

Two smaller decisions follow from the same place: what happens when a selection
exceeds the budget, and whether the budget belongs in the fingerprint.

# Decision

1. **The budget is a required argument with no default.** The caller supplies it;
   it is recorded in the manifest; nothing is assumed. A default would silently
   become part of every fingerprint ever recorded.
2. **The unit is an exact word count**, named `harness.compile.tokens.UNIT =
   "word"`. It is deterministic and provider-independent — a property a
   reproducible compiler needs — and the code never calls it a "token".
3. **Adopting a model tokenizer is a `DecisionRequired`.** If a budget must be
   expressed in a model's tokens, that becomes a recorded decision with its own
   consequences (which tokenizer, which version, whether old fingerprints are
   comparable). The compiler does not presume it.
4. **Refuse rather than truncate**, and give the refusal its own exit code:
   blocked `3`, uncovered `4`, over budget `5`, usage `2`.
5. **The budget does not enter the fingerprint.** It bounds whether a prompt is
   admissible, not its content. A generous and a tight budget compile the same
   prompt, and the fingerprint says what was sent.

# Consequences

- A fingerprint always corresponds to exactly one prompt; the budget cannot be
  varied to produce a different prompt under the same fingerprint.
- No invented threshold exists anywhere in the code. `harness compile` fails
  loudly and immediately if `--budget` is omitted, which is the correct
  behaviour when a value is undecided.
- Refusing on over-budget is deliberately all-or-nothing. Dropping documents
  would be a **false claim** about what binds the work item, and the failure is
  invisible: the model would answer confidently from partial context. An operator
  who wants to see the selection uses `harness context`, which lists it without
  truncating either.
- Cost: a caller must know what budget they want, or compile with a large one and
  read `used` from the manifest to discover the true size. That is a deliberate
  trade: an assumed default is worse than a supplied number.
- Migration note: if the unit ever changes, every previously recorded fingerprint
  stays valid *for its own unit* — they are content hashes, not unit hashes — but
  budgets recorded before and after are not comparable. The `unit` is stored in
  the manifest so that is detectable rather than guessed.

# Alternatives rejected

- **A default budget.** Invented, and it would silently shape every fingerprint.
- **The provider's tokenizer.** Makes the budget provider-specific and the
  fingerprint fragile; also picks a dependency the project has not decided to take.
- **A character count.** Provider-independent, but a worse proxy for the thing the
  budget is trying to bound.
- **Truncate and record what was dropped.** Tempting and wrong: the model receives
  partial context and the prompt reads as complete; recording the omission does not
  undo the answer it produces.
- **Exclude the budget from the manifest to avoid coupling.** The manifest is an
  audit record of the bounding decision; omitting the bound would hide it.
