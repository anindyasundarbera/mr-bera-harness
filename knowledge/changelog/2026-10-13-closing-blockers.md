---
type: Changelog Entry
id: CHG-2026-016
date: 2026-10-13
kind: fixed
title: Closed the recorded blockers — two defects fixed, four status-quo records added
summary: Fixed the generated header hardcoding a source path and the dashboard reporting a vacuous routing pass, and recorded four previously-open items as ADRs stating what the code does today, what was chosen implicitly, and which parts remain the owner's decision.
covers: [MRB]
---

Closing the blockers meant separating two kinds of item that had been listed
together.

## Two mechanical defects, fixed

**1. A generated file stated a location it was not told.**
`docs/DECISIONS_INDEX.md` said the authoritative entries live in
`knowledge/decisions/`, while `harness.toml` configures `docs/decisions` — and the
text was **hardcoded** in `entries/generator.py`. This is the same class as the four
location defects already fixed: a library answering about its own context instead of
its caller's. The renderers now take the configured path, so the header states where
*this* project keeps its entries. Two tests pin it, including the exact case that
exposed it.

**2. The dashboard reported a vacuous pass.**
`routing invariants  pass  0 violation(s) over 0 concept(s)` — a pass over
**nothing checked**. The harness's own bundle triggers it, because `validate_routing`
deliberately skips changelog and decision entries, which is all that bundle holds. It
is now `unknown` with the reason stated, applying the dashboard's own three-valued
rule to itself. A test covers it.

## Four items recorded at their true status

An ADR each, stating what the code does today and which parts remain the owner's —
because inventing a PostgreSQL version or a credential policy is exactly what must
not happen:

| Record | What it settles | What stays open |
|---|---|---|
| `ADR-2026-014` | no version pinned anywhere; the index is rebuild-on-demand; the `postgres:16` image in CI is a **test fixture, not a support claim** | the supported version range, locality, whether a long-running service is ever wanted |
| `ADR-2026-015` | workflow changes route over SSH with the owner's key; no credential shared or widened; the `gh`-says-SSH-while-origin-is-https hazard recorded | whether to widen the credential (recommended: a narrow, revocable token) or keep this route permanently |
| `ADR-2026-016` **`Proposed`** | `harness ci` runs the harness's own stages in a consumer and misdiagnoses it; `default_pipeline()`'s docstring promises a consumer behaviour that does not exist | refuse clearly vs make it configurable — both touch the `harness.toml` schema |
| `ADR-2026-010`, `ADR-2026-012` | already recorded the budget unit and the validator dependency | the tokenizer choice |

`ADR-2026-016` is deliberately **`Proposed`**, not `Accepted`: it documents a defect
and the fix is undecided. An `Accepted` record describing unimplemented behaviour
would be a false record.

**Tests:** 513 without a database; coverage unchanged at 91.1%. Lint, format,
`mypy --strict`, `harness doctor`, `harness guards` and `harness ci` all clean.

## Follow-up: the handoff itself had gone stale

Refreshing `docs/design/REMAINING_WORK.md` for this session's handoff found it
described steps 1–3 as the state and steps 4–6 as "not started" — by then all six were
merged. A handoff that is wrong is worse than none, because it is trusted.

Corrected: the build-order table now lists all six plus the four capabilities built
beyond it; the historical step 4–6 narrative is replaced by a map to each step's design
note and decision record rather than a summary that would be a second copy to keep in
step; the decision table shows entry-location **closed** and adds the two items this
session surfaced; and the verification section no longer says "after step 3 merges".
