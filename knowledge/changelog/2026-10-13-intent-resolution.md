---
type: Changelog Entry
id: CHG-2026-018
date: 2026-10-13
kind: added
title: Instruction to work item — resolved when unique, asked when not
summary: Implemented build-order step 6, the one step rated not deterministic, as a resolver that extracts identifiers the instruction names, scores the decomposition lexically, and refuses with a clarification request whenever the answer is not unique, calling no model.
covers: [MRB]
---

Implements build-order step 6 of `HARNESS_ARCHITECTURE.md` §9 — *human intent to
compiled prompt* — the last component and the only one the architecture rates **not
deterministic**.

```bash
harness intent resolve "work on MRB-M06-S07"
harness intent resolve "the model set and hardware envelope"
harness intent resolve "whatever I meant" --work-id MRB-M06-S01 --budget 4000
```

## What §8 permits, implemented exactly

§8 says a fuzzy classifier is not achievable and states what to build instead:
*deterministic prompt **assembly**; intent resolution is explicit and fallible, with a
human-clarification fallback.* So this is not a classifier:

1. **Exact extraction** — identifiers the instruction already contains, per the
   configured grammar. Not inferred: the grammar decides.
2. **Lexical scoring** — against each declared identifier *and the concepts that cover
   it*, so a phrase can reach an identifier through a concept title.
3. **Refusal** — two candidates, a tie, a close runner-up, or nothing above the cut is
   a **clarification request**, never a pick.

**No model, no network, no shell.** §4's rule is explicit that a model in the
extraction path makes the system *"probabilistic wearing a deterministic label"*.

## The refusal is the feature

§9 says the design must not depend on this step, which makes a wrong guess **worse**
than no answer: it would compile a prompt bound to the wrong work item and present it
as authoritative — and nothing downstream would catch it, because everything after is
deterministic.

| Situation | Status | Exit |
|---|---|---|
| exactly one identifier named | `resolved` | 0 |
| one candidate above the cut, no close runner-up | `resolved` | 0 |
| two or more identifiers named | `ambiguous` | 3 |
| candidates tied, or a leader within 80% of a runner-up | `ambiguous` | 3 |
| nothing above the cut | `unresolved` | 4 |

Observed on a real corpus:

```
$ harness intent resolve "the model set and hardware envelope"
status : ambiguous
reason : `MRB-M06-S03` leads on 0.50 but `MRB-M06-S07` is close on 0.40; ask which
```

A leader at 0.50 against 0.40 is real signal and still a question. And an explicit
`--work-id` bypasses resolution entirely — the architecture's point that a human
naming the ID loses nothing — with the reason stating *"nothing was inferred"* rather
than pretending it resolved something.

## Two bugs found while building, both about the identifier grammar

1. **The validating grammar cannot scan.** `identity.id_pattern()` is anchored
   (`\A…\Z`), so `re.search` with it never matches inside prose — an instruction
   naming `MRB-M06-S07` resolved to *nothing*, the most common case failing.
2. **The scan pattern lost the nesting.** Concatenating the level groups made every
   level mandatory, so it matched almost no real identifier. The validating grammar
   *nests* its optional groups; the scan pattern now nests identically.

Both were caught by tests describing *behaviour* — a one-level identifier must work —
rather than implementation.

## Project-agnostic, verified in a fresh consumer

A `EPIC` prefix with `P/S` levels, a `kb/` bundle, `specs/` docs:

| Instruction | Result |
|---|---|
| `work on EPIC-P01-S01` | `resolved` |
| `EPIC-P01 and EPIC-P01-S02` | `ambiguous` (exit 3) |
| **`the ledger writer`** | `resolved` → `EPIC-P01-S01`, reached via the *concept* title |
| `something entirely unrelated here` | `unresolved` (exit 4) |

The third row is why scoring uses concepts: a phrase in no identifier reached the
right one.

**Tests:** 557 without a database; **629 with a live PostgreSQL**, coverage 91.5%
(`intent/resolve.py` 98%). Lint, format, `mypy --strict`, `harness doctor`,
`harness guards` and `harness ci` all clean.
