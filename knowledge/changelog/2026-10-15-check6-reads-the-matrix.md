---
type: Changelog Entry
id: CHG-2026-026
date: 2026-10-15
kind: fixed
title: Routing check 6 read the wrong thing, and could pass vacuously
summary: Redefined check 6 to read the state-ownership matrix from the routing contract instead of inferring ownership from frontmatter, so a do_not_use_for listing is treated as the disclaimer the contract defines rather than a claim; it also read only one spelling of the field, which made it see 0 of 90 keys on spec-conformant documents.
covers: [MRB]
---

Routing check 6 was documented as *"no `do_not_use_for` key is claimed by two modules"* and
implemented by grouping listings by module. Three things were wrong, and **all three were
invisible while M06 was the only module.**

## 1. It inverted the field's meaning

`DOCUMENT_ROUTING.md` §4's usage rule: *"an M06 document listing `commerce-truth` means this
document must **not** be used to define price — that is M03's."* A listing is a **disclaimer**;
the check counted it as a **claim**.

Three independent sources agree with the prose: the usage rule, **M06's own data** (it lists
**9 keys it does not own** and **0 it does**), and the **resolver**, whose only use of the
field is exclusion — *"excluded when its `do_not_use_for` names a state the caller intends to
define"* — which is coherent only as a disclaimer. Under the claim reading the resolver would
exclude a document *because it owns the state*.

## 2. The harness's own test pinned the inversion in place

`test_two_modules_claiming_one_key_detected` asserted that two modules listing one key **is** a
violation. That test is now rewritten to assert the opposite, with its docstring saying why.

## 3. It read one spelling, and went **vacuous**

The contract writes `do-not-use-for`; OKF concepts use `do_not_use_for`. Check 6 read the
underscored form only. Measured on spec-conformant documents: **0 of 90 keys seen** —
`routing invariants: 0 violation(s)` while the guard had not run. **A guard that reports clean
without checking is worse than one that is wrong, because it is indistinguishable from a
pass.**

## Why it surfaced now

All three are harmless for a single-module bundle: no key can be listed by two of one module,
and the spelling in use is the one the code reads. Authoring **M05, M07 and M03** for
`FRAMEWORK-007` supplied the **first second module** — and 13 false collisions appeared. The
check could never have passed for a repository with more than one module.

## The fix

Ownership is now read from the contract's matrix — the authority §4 names — via a new
`state_ownership()` and a `paths.routing` config key (no hardcoded filename). A disclaimer is
verified for the two things that actually matter: **the key is real**, and **the disclaiming
module is not its owner**. Both spellings are read. `owners_key()` is deleted.

## Measured

| | Before | After |
|---|---|---|
| `mr_bera` routing violations | **13** | **0** |
| Matrix keys seen | 0 (hyphen spelling) | **14** |
| Fires on a real violation | n/a | **verified by injection** |

The 13 were not defects in the documents — they were the check misreading correct disclaimers.

**Tests:** 633 without a database (4 new). `doctor` clean, `mypy --strict` clean, ruff and
format clean, `harness ci` PASSED.

**Cost, stated:** when the contract is absent, `state_ownership()` returns empty and the per-key
checks are skipped — a silent degradation in a new place. Mitigated by it being detectable, and
by a project without a contract having no ownership rules to enforce.

Refs: ADR-2026-024
