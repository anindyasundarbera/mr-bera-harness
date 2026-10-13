---
type: Decision Record
id: ADR-2026-012
date: 2026-10-13
title: The gates validate against JSON Schema via the standard library, and may not execute
status: Accepted
decision: Validate proposals against JSON Schema using the jsonschema package as an optional extra, and keep the effect gates strictly verdict-returning with no code path to a mutation.
covers: [MRB]
supersedes: []
---

# Context

Build-order step 4 defines what a model may propose and how a proposal is checked.
Two questions had to be settled, and both have a tempting wrong answer.

**1. What validates the proposal?** `HARNESS_ARCHITECTURE.md` §10.1 records the
validated finding directly: "**Schema is enforced; semantics are not.**" Native
Ollama `format: <JSON Schema>` enforced structure at the sampling layer under an
adversarial prompt, and every adversarially steered model still returned a
*structurally valid* proposal. So the schema is the contract the provider
enforces, and it must be a real JSON Schema — the exact document handed to the
provider must be the document used locally, or the two definitions of validity
drift.

The temptation is to hand-roll a small validator to avoid a dependency. That
creates a second, subtly different definition of "valid": it would accept
documents the provider rejects, or reject documents it accepts, and the failure
would appear only at the boundary between them.

**2. What does a gate do?** `ADR-2026-005` gives the harness every execution and
the model none. The same architecture says (§7) to prefer the *impossible* class
over the *loud* class. A gate that had the ability to execute would be a second
executor, and one that had a "fix it up" path would be a mutation the model
influenced.

# Decision

1. **JSON Schema, via `jsonschema`, as an optional extra (`.[propose]`).** The
   standard implementation of the format §10.1 names. The same `PROPOSAL_SCHEMA`
   dict is printed by `harness propose schema` for a provider and used locally, so
   one document defines validity in both places.
2. **A missing validator is a loud failure, never a silent pass.** `validator()`
   raises with the install command in the message. A gate that could not validate
   must not report a verdict.
3. **Gates return a verdict and execute nothing.** No mutation path exists in
   `harness/propose/`; a test asserts no mutation or network machinery is imported
   and that gating leaves the tree byte-identical.
4. **Three-valued verdicts** — `permitted`, `refused`, `not-checked` — and
   `may_execute` is true only when **every** gate is `permitted`. A rule that
   cannot be evaluated blocks execution rather than passing.
5. **The policies are §7.1's enumerated rules, cited by name in the code.** A test
   asserts all six rules are covered, so a policy cannot be invented and a rule
   cannot be dropped silently.
6. **The schema is versioned** (`PROPOSAL_SCHEMA_VERSION`), following
   `MODEL_VERSION` and `INDEX_SCHEMA_VERSION`. A proposal states the contract it
   was made against.

# Consequences

- **One definition of validity.** The document given to the provider is the
  document enforced locally, so the two cannot disagree.
- **The propose/dispose split is structural.** Because there is no code path from
  a verdict to a mutation, "the model executes nothing" is a property of the code
  rather than a discipline an agent is asked to observe.
- **`not-checked` blocks.** A session that has declared no change manifest cannot
  be checked against "one logical change per branch", so a write proposes
  `not-checked` and does not execute. Declaring the manifest at session start is
  what makes the rule checkable — the gate makes the omission visible instead of
  assuming compliance.
- **The `branch` field is judged as the branch *named*, not the current branch.**
  Refusing to *start* on a protected branch is the session guard's job
  (`ADR-2026-004`); duplicating it here would be a second, divergent answer. So
  creating a branch called `main` is refused — it targets a protected branch —
  while creating `feat/x` is the intent that leaves one.
- Cost: a new optional dependency. It is an extra, the package's core dependency
  count is unchanged, and the proposal tests skip cleanly without it — verified in
  a venv that omits it.

# Alternatives rejected

- **A hand-rolled validator.** A second definition of validity that would drift
  from the provider's, failing at the boundary rather than in a test.
- **Prompts that ask the model to obey the schema.** §10.1 rejected this
  experimentally: constrained decoding enforces at the sampling layer, and a
  prompt cannot.
- **Gates that return a boolean.** "Not checked" is a real outcome — an
  undeclared manifest, an absent validator — and a boolean would call it either a
  pass (unearned) or a refusal (wrong, and it would train a reader to ignore
  refusals).
- **Letting a gate perform the action it permits.** That is a second executor,
  and it makes the model's proposal, rather than the harness's code, the thing
  that decides what happens.
- **Requiring the dependency unconditionally.** Proposals are one capability among
  several; a consumer that does not gate proposals should not have to install a
  validator, and does not.
