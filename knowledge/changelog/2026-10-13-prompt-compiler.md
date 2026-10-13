---
type: Changelog Entry
id: CHG-2026-009
date: 2026-10-13
kind: added
title: Prompt compiler — a work item in, a bounded prompt and a fingerprint out
summary: Implemented build-order step 3, compiling a task ID plus a caller-supplied budget into a deterministic prompt with a SHA-256 fingerprint that binds its content; over-budget and blocked work items are refused rather than truncated.
covers: [MRB]
---

Implements build-order step 3 of `HARNESS_ARCHITECTURE.md` §9: *task ID +
selection + budget → prompt + fingerprint*. Deterministic — no model, no clock,
no network.

## What it does

Selection comes from `harness.routing.resolve`; text comes from the same
`git archive` materialization step 1 introduced, so the prompt is a **pure
function of a committed revision**. `harness compile <work-id> --budget N` prints
the prompt on stdout and the fingerprint on stderr, so a caller can capture either
without the other. `--json` carries both; `--manifest` carries the audit record
without the text.

## The fingerprint is the §3 dashed edge, made executable

The architecture calls the pre-call fingerprint *load-bearing*: without it a
session cannot be reproduced and "deterministic" is an unevidenced claim. The
digest covers the prompt text **and the manifest** of which documents are in it —
concept id, path, title, read budget, trust tier, status, staleness, coverage and
per-entry size.

Hashing the text alone would let a same-length document be substituted without the
digest changing. A test asserts the structure binds.

## No invented threshold

`--budget` is **required with no default**. No authoritative document fixes a
value, and a default would silently become part of every fingerprint. The unit is
an exact **word** count, named in `harness.compile.tokens.UNIT` — deterministic
and provider-independent, which is what a reproducible compiler needs. It is not
called a "token", because a token depends on the model's tokenizer and would make
the budget provider-specific. Adopting a tokenizer is recorded as
`DecisionRequired` in `ADR-2026-010`.

The budget bounds admissibility, not content, so it does **not** enter the
fingerprint: a generous and a tight budget compile the same prompt.

## Refusal, not truncation

| Condition | Exit |
|---|---|
| blocked | `3` |
| nothing covers the chain | `4` |
| over budget | `5` |
| usage error | `2` |

Over budget is all-or-nothing on purpose. Dropping documents would be a **false
claim** about what binds the work item, and the failure is invisible — the model
would answer confidently from partial context. `harness context` remains available
for discovery. `--defining` is passed through, so a concept whose `do_not_use_for`
names a state the caller intends to define appears in the manifest as **excluded**
rather than vanishing.

## Verified

- 35 compiler tests and 9 CLI tests: determinism, fingerprint binding, every
  refusal path, exclusion, manifest.
- Same revision compiles byte-identical text and fingerprint; an uncommitted edit
  changes neither; a committed edit changes both.
- Real consumer corpus: `MRB-M06-S01` compiles 10 documents / 2582 words /
  fingerprint `395fe52f…`, **identical across runs**; `MRB-M06-S07` refuses with
  exit 3 naming `DESIGN-RUBRIC-01`, `EVID-AI-HW-01`, `IMG-DIM-01`.
- A malformed work identifier is reported as a usage error rather than escaping as
  an uncaught `OkfError` — found by a test, fixed.

**Tests:** 382 passing without a database; **448 with a live PostgreSQL**,
coverage 91.3%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards`
and `harness ci` all clean.
