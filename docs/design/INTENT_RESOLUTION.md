---
id: HARNESS-INTENT-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, PROMPT_COMPILER.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Instruction → prompt

> ID: HARNESS-INTENT-001
>
> Status: **Implemented** — build-order step 6 of `HARNESS_ARCHITECTURE.md` §9, the
> one step rated **not deterministic**. The design and its limits are `ADR-2026-018`.

---

## 1. What this is

Build-order step 6: *human intent to compiled prompt*. The last component, and the
only one the architecture says is not deterministic:

> **Step 6 is last because it is the least provable**, and the design must not depend
> on it: a human who writes the task ID directly bypasses step 6 entirely and loses
> nothing.

§8 states exactly what can be built instead of a classifier:

> Fully deterministic instruction→prompt | Intent classification is fuzzy |
> **Deterministic prompt *assembly*; intent resolution is explicit and fallible, with
> a human-clarification fallback**

So this step is not a classifier. It is a **resolver that refuses**.

```bash
harness intent resolve "work on MRB-M06-S07"
harness intent resolve "the model set and hardware envelope"
harness intent resolve "whatever I meant" --work-id MRB-M06-S01 --budget 4000
```

## 2. Three things, and no fourth

1. **Exact extraction.** Work identifiers the instruction *already contains*,
   according to the project's configured grammar. Not a guess — the grammar decides.
2. **Lexical scoring.** Every identifier the decomposition declares is scored against
   the instruction, and against the **concepts that cover it**, so a phrase can reach
   an identifier through a concept title rather than only through its own name.
3. **Refusal.** Two candidates, a tie, a close runner-up, or nothing above the cut is
   a **clarification request** — never a pick.

Nothing here calls a model. The scoring is lexical and deterministic; a semantic
resolver would be a different, non-reproducible thing and is deliberately not this.

## 3. The refusal is the feature

`§9` says the design must not depend on this step. That makes a wrong guess strictly
**worse** than no answer: a mis-resolved instruction would compile a prompt bound to
the wrong work item and present it as authoritative.

| Situation | Status | Exit |
|---|---|---|
| exactly one identifier named | `resolved` | 0 |
| exactly one candidate above the cut, with no close runner-up | `resolved` | 0 |
| two or more identifiers named | `ambiguous` | 3 |
| several candidates tied | `ambiguous` | 3 |
| a leader within 80% of a runner-up | `ambiguous` | 3 |
| nothing above the cut | `unresolved` | 4 |

Observed on a real corpus:

```
$ harness intent resolve "work on MRB-M06-S07"
status : resolved   work item : MRB-M06-S07

$ harness intent resolve "the model set and hardware envelope"
status : ambiguous
reason : `MRB-M06-S03` leads on 0.50 but `MRB-M06-S07` is close on 0.40; ask which

$ harness intent resolve "MRB-M06 and MRB-M07"
status : ambiguous
reason : the instruction names 2 work identifiers; ask which
```

A leader at 0.50 against 0.40 is a real signal and still a question — the answer
being asked for is *which*, and both are plausible.

## 4. Two bugs found by building it, both about the grammar

**1. The validating grammar cannot scan.** `identity.id_pattern()` is anchored
(`\A…\Z`) because it validates a whole identifier, so `re.search` with it can never
match inside prose. An instruction naming `MRB-M06-S07` therefore resolved to
*nothing* — the most common case failing. Fixed with `scan_pattern()`, the same
grammar without anchors.

**2. The scan pattern lost the nesting.** The first `scan_pattern` concatenated the
level groups, making every level mandatory, so it matched almost no real identifier.
The validating grammar **nests** its optional groups — each level required relative
to its parent, so `MRB-M06` matches and no level is skipped. The scan pattern now
nests identically, and a test pins both a one-level and a two-level identifier.

Both were caught by tests written to describe the *behaviour*, not the implementation
— which is why the tests were specific about a one-level identifier working.

## 5. Project-agnostic, verified in a consumer

Everything comes from configuration:

- the scan pattern from `identity.prefix/levels/widths`;
- the known identifiers from the project's decomposition document;
- concept titles from the bundle at `paths.knowledge`.

Verified in a fresh consumer sharing nothing with this repository — a `EPIC` prefix
with `P/S` levels, a `kb/` bundle, `specs/` docs:

| Instruction | Result |
|---|---|
| `work on EPIC-P01-S01` | `resolved` |
| `EPIC-P01 and EPIC-P01-S02` | `ambiguous` (exit 3) |
| **`the ledger writer`** | `resolved` → `EPIC-P01-S01` — reached via the *concept* title |
| `something entirely unrelated here` | `unresolved` (exit 4) |
| `--work-id EPIC-P01` | `resolved`, *"nothing was inferred"* |

The third row is the point of scoring against concepts: a phrase that appears in no
identifier reached the right one.

## 6. What it does not claim

- **It is not a classifier.** It does not infer intent from prose; it finds
  identifiers and scores lexical overlap. A paraphrase with no shared words is
  `unresolved`, which is the honest answer, not a failure.
- **It does not validate the work item.** An identifier the decomposition does not
  declare still resolves — new work is legitimate — and the reason says so.
- **It is not a gate.** A resolved work item still meets the compiler's refusals: a
  blocked item still exits 3, an uncovered chain still exits 4.
- **Nothing executes.** No network, no shell, no model, and resolving leaves the
  working tree byte-identical — asserted by a test.

## 7. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Build-order step 6 implemented: exact extraction, lexical scoring, refusal on ambiguity, verified in a consumer. |
