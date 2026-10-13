---
id: HARNESS-PROPOSE-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, PROMPT_COMPILER.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Proposal schemas and effect gates

> ID: HARNESS-PROPOSE-001
>
> Status: **Implemented** — build-order step 4 of `HARNESS_ARCHITECTURE.md` §9.
>
> Authority: a design document. The dependency and no-execution decisions are
> `ADR-2026-012`.

---

## 1. What this is

Build-order step 4: *what the model may propose, and how a proposal is checked*.

This is the first step with a model in the loop, and the one where the
propose/dispose split stops being a diagram and becomes code. The model returns a
proposal; the harness decides whether to act on it. **Nothing in this step acts.**

```bash
harness propose schema                  # the JSON Schema, for handing to a provider
harness propose validate proposal.json  # structure only
harness propose gate proposal.json      # structure + every policy
```

## 2. The split §10.1 proved, made executable

`HARNESS_ARCHITECTURE.md` §10.1 validated constrained decoding on the target
runtime and drew the conclusion this step is built on:

> **Schema is enforced; semantics are not.** Every adversarial model returned a
> *valid* proposal that the attack had steered.

Both halves are needed and neither is sufficient. The provider enforces structure;
the gates check meaning. The code demonstrates the gap rather than describing it —
this proposal is **fully schema-valid** and still refused:

```json
{"schema_version": 1, "work_id": "MRB-M06-S01", "intent": "push",
 "summary": "Push finished work", "branch": "main", "test_effect_passed": true}
```

```
$ harness propose validate …   → exit 0   (schema-valid; the provider would allow it)
$ harness propose gate …       → exit 2   (refused: `main` is a protected branch)
```

## 3. The contract is versioned, and it is one document

`PROPOSAL_SCHEMA` is a single dict that is both printed for a provider and used
locally, so one document defines validity in both places. It carries
`$id: …/proposal-v1.json` and `PROPOSAL_SCHEMA_VERSION`, following
`MODEL_VERSION` and `INDEX_SCHEMA_VERSION` — a schema change invalidates a
recorded proposal, and a proposal that does not state its contract cannot be
checked against the right one.

`additionalProperties: false`, so a key cannot be smuggled in. Conditional
requirements, so an intent that needs a field is **structurally invalid** without
it: a `write_file` with no `work_packet` cannot be expressed at all, which is a
stronger form of the rule than a gate that refuses it.

## 4. The policies are §7.1's rules, cited

The schema's `intent` enum is derived from the rules the architecture already
enumerates, not invented here. Each gate cites the rule it enforces, and a test
asserts all six are covered — so a rule cannot be dropped silently and a policy
cannot be invented.

| Rule (§7.1) | Gate |
|---|---|
| `do not write code unless explicitly instructed` | a write needs an approved work packet |
| `switch to a new branch for new development` | the named branch must match configured policy |
| `test before push` | a push needs the in-session test effect-check passed |
| `never commit a secret` | the target path must not match the forbidden globs |
| `one logical change per branch` | the target path must be inside the declared manifest |
| `write a decision, not a memory` | a decision must name an entry file |

Plus one mechanism the architecture does not enumerate separately but which makes
`never commit a secret` real: **a path may not escape the project root**. An
allow-list that tests a raw string can be walked around with
`knowledge/../../.env`, so paths are normalized before they are judged.

## 5. Verdicts are three-valued, and `not-checked` blocks

| Verdict | Meaning |
|---|---|
| `permitted` | every gate passed |
| `refused` | a gate found a violation |
| `not-checked` | a gate could not evaluate its rule |

`may_execute` is true **only** when every gate is `permitted`. `not-checked`
blocks, because the harness does not act on a precondition it could not evaluate.
The concrete case is the change manifest: a session that declared none cannot be
checked against `one logical change per branch`, so a write reports `not-checked`
and does not proceed. That makes the omission visible instead of assuming
compliance.

The gate judges the branch a proposal **names**, not the branch the session is on.
Refusing to *start* on a protected branch is the session guard's job
(`ADR-2026-004`); duplicating it here would be a second, divergent answer. So
creating `feat/x` is permitted — it is the intent that leaves a protected branch —
while creating a branch *called* `main` is refused, because it targets one.

## 6. Nothing here executes

There is **no code path from a verdict to a mutation**. That is what makes "every
mutation has exactly one executor, and it is not the model" a property of the
code rather than a discipline an agent is asked to observe. A test asserts it:
neither module imports `os`, `subprocess`, `shutil`, `socket`, `urllib` or
`requests`; neither calls `open` or any write method; and gating the same proposal
three times leaves the tree byte-identical.

The only file written anywhere in this step is a proposal file the caller supplies.

## 7. The validator is an optional extra

`jsonschema` is the standard implementation of the format §10.1 names, installed
via `.[propose]`. Hand-rolling a subset would create a second definition of
validity that drifts from the provider's and fails at the boundary rather than in
a test.

A **missing validator is a loud failure**, never a silent pass: `validator()`
raises with the install command in the message. The proposal tests skip cleanly
without the extra — verified in a venv that omits it — so a consumer that does not
gate proposals is not obliged to install one. CI installs the extra, so the tests
run there.

## 8. Exit codes

| Code | Meaning |
|---|---|
| `0` | permitted (or the schema was printed) |
| `1` | structurally invalid |
| `2` | refused by a gate |
| `3` | not checked |
| `4` | usage error |

`1` and `2` are deliberately distinct: "this is not a well-formed proposal" and
"this is well-formed and not allowed" are different findings, and §10.1 exists
precisely because conflating structure with meaning hides the second.

## 9. Deliberately not here

| Not built | Why |
|---|---|
| Executing a permitted proposal | that is the executor, a later concern; this step is the decision only |
| Calling a model to obtain a proposal | the harness owns the loop (`ADR-2026-005`); §10.1 covers the provider side |
| A gate that repairs a proposal | repair is a mutation influenced by the model |
| Policy values not in §7.1 | a rule the architecture does not name is not enforced here |

## 10. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Build-order step 4 implemented: versioned schema, six rule-citing gates, three-valued verdicts, no execution path. |
