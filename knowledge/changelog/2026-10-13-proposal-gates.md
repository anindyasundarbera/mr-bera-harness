---
type: Changelog Entry
id: CHG-2026-013
date: 2026-10-13
kind: added
title: Proposal schemas and effect gates — what may be proposed, and what is refused
summary: Implemented build-order step 4, a versioned JSON Schema for proposals plus gates that enforce the six rules architecture 7.1 enumerates, returning a three-valued verdict and never executing anything.
covers: [MRB]
---

Implements build-order step 4 of `HARNESS_ARCHITECTURE.md` §9: *what the model may
propose, and how a proposal is checked*. The first step with a model in the loop —
and the one where the propose/dispose split becomes code rather than a diagram.

```bash
harness propose schema                  # the JSON Schema, for a provider
harness propose validate proposal.json  # structure only
harness propose gate proposal.json      # structure + every policy
```

## The §10.1 split, demonstrated rather than described

Structure is the provider's job; meaning is the harness's. §10.1 established that
constrained decoding enforces the schema at the sampling layer and that
**semantics are not enforced** — every adversarially steered model returned a
*valid* proposal.

The code shows the gap. This proposal is **fully schema-valid** and still refused:

```
$ harness propose validate …   → exit 0   (the provider would allow it)
$ harness propose gate …       → exit 2   (refused: `main` is a protected branch)
```

`1` (structurally invalid) and `2` (refused) are distinct exit codes for exactly
this reason: conflating structure with meaning hides the second case.

## The policies are the architecture's own rules

The `intent` enum is derived from the rules §7.1 already enumerates; each gate
cites the rule it enforces; a test asserts all six are covered, so a rule cannot
be dropped and a policy cannot be invented. The schema also enforces each intent's
required fields **conditionally**, so a `write_file` with no work packet is
structurally invalid — a stronger form of the rule than a gate that refuses it.
`additionalProperties: false` stops a key being smuggled in.

One mechanism the architecture does not enumerate but which makes
`never commit a secret` real: **a path may not escape the project root**.
Normalizing first is what closes `knowledge/../../.env`.

## Three-valued verdicts, and `not-checked` blocks

`permitted` / `refused` / `not-checked`, and `may_execute` is true only when every
gate is `permitted`. A session that declared no change manifest cannot be checked
against `one logical change per branch`, so a write reports `not-checked` and does
not proceed — the omission becomes visible instead of being assumed compliant.

The gate judges the branch a proposal **names**, not the branch the session is on:
creating `feat/x` is the intent that leaves a protected branch, while creating a
branch *called* `main` is refused. Refusing to *start* on a protected branch
remains the session guard's job (`ADR-2026-004`) rather than a second answer here.

## Nothing executes

There is no code path from a verdict to a mutation — asserted, not asserted-in-
prose: a test checks that neither module imports `os`, `subprocess`, `shutil`,
`socket`, `urllib` or `requests`, calls no write method, and that gating the same
proposal three times leaves the tree byte-identical.

## One new optional dependency

`jsonschema` via `.[propose]`, the standard implementation of the format §10.1
names. A hand-rolled subset would be a second definition of validity that drifts
from the provider's and fails at the boundary instead of in a test. A missing
validator is a **loud failure, never a silent pass**; the tests skip cleanly
without the extra (verified in a venv that omits it), and CI installs it.

## Two bugs found by the tests

1. **The gate permitted creating a branch called `main`.** It had special-cased
   `create_branch` on a protected branch, conflating the branch *named* with the
   branch *occupied*. Corrected, and the two cases are now separate tests.
2. **A manifest of `.` did not cover every path**, because `.env.example` is not
   prefixed by `"./"`. Corrected, with a test for the whole-project case.

**Tests:** 482 without a database; **548 with a live PostgreSQL**, coverage 91.5%.
Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and `harness ci`
all clean; CI matrix and the CI shape both pass.
