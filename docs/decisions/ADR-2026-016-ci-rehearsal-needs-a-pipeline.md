---
type: Decision Record
id: ADR-2026-016
date: 2026-10-13
title: The local CI rehearsal refuses to run a project it has no pipeline for
status: Proposed
decision: Record that harness ci runs the harness's own stages when invoked in a consumer, which misdiagnoses the consumer as broken; the fix is undecided between refusing clearly and adding a configurable pipeline, and both touch a configuration schema that already has an open decision.
covers: [MRB]
supersedes: []
---

# Context

`harness ci` rehearse the pipeline locally (`ADR-2026-003`). Invoked in a repository
other than the harness, it runs **the harness's own stages** — wheel build,
`mypy src`, the `selfcheck` steps — and fails with a message that implies the
*consumer* is broken:

```
$ harness ci          # in a consumer repository
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
RESULT: FAILED — package, typecheck, test, selfcheck
```

This was found by testing the harness against a fresh consumer repository — no unit
test could have found it, because the suite runs *inside* the harness where that
pipeline is correct.

It is the same class as the four location defects already fixed (`guards/session.py`,
`entries/commits.py`, `entries/generator.py`, `ci/rehearse.py`): the library
answering a question about its own context rather than its caller's. It also
contradicts `ci/rehearse.py`'s own docstring — *"A consumer defines its own `Pipeline`
directly; this default exists only so the harness can dogfood itself"* — so the
documented consumer behaviour does not exist.

# Decision

**Status: `Proposed` — this record documents a defect. Nothing described here is
implemented, and it must not be read as though it were.** The behaviour below is
what the code does *today*; the fix is undecided.

**Recorded as fact about the current behaviour:**

1. `harness ci` runs the harness's own stages regardless of which repository it is
   invoked in, so in a consumer every stage fails for a reason unrelated to the
   consumer.
2. `default_pipeline()` is explicitly the harness dogfooding itself, and its own
   docstring says a consumer defines its own `Pipeline` directly — a consumer-facing
   behaviour that does not exist.
3. No configuration key exists for a consumer pipeline, so there is currently no way
   to make `harness ci` correct in a consumer at all.

**Remaining the owner's decision — the shape of the fix:**

- **Option A — refuse clearly.** `harness ci` in a project with no declared pipeline
  exits with a message like "no pipeline is configured for this project; see
  docs/…". Minimal, honest, and leaves the command unusable in a consumer until a
  pipeline is declared.
- **Option B — make it configurable.** `harness.toml` gains a `[ci]` section (stage
  commands, or a path to a pipeline definition) so a consumer declares its own
  rehearsal and `harness ci` becomes genuinely project-agnostic. More work, more
  useful, and it extends the project's configuration schema.

The agent's view, as input rather than as the decision: **Option B is the better
eventual shape** — the module's own documentation already promises it — but Option A
is the smaller, safer step and would remove the misdiagnosis immediately.

Both options touch the same `harness.toml` schema that open decision 1 (the budget
unit) and the dashboard already read, so whichever is chosen should be recorded
before the schema grows further.

# Consequences

- **The defect is documented rather than rediscovered.** It cost a consumer test to
  find; the next agent reads it.
- **CI is unaffected.** CI runs `ci.yml`, not `harness ci`. No shipped capability
  depends on this command in a consumer, so the impact is bounded to a confusing
  local failure.
- **The misdiagnosis is the real harm.** A consumer sees "FAILED — package,
  typecheck, test, selfcheck" and reasonably concludes their repository is broken;
  the truth is that they asked the harness to rehearse a pipeline nobody declared.
  Recording that distinction is the point of this decision.
- Cost: until the owner chooses, `harness ci` remains wrong in a consumer. That is a
  known, recorded limitation rather than a latent trap.

# Alternatives rejected

- **Fix it now with a guess.** The choice between refusing and configuring changes
  the configuration schema, and the schema is already the subject of another open
  decision. Guessing here would create a second, conflicting decision about the same
  file.
- **Leave it undocumented.** It has already misdiagnosed once. A recorded limitation
  costs one page; a rediscovered defect costs a session.
- **Make `default_pipeline()` detect a consumer and switch behaviour.** Behaviour that
  depends on undetectable intent stays surprising; an explicit pipeline or an explicit
  refusal does not.
