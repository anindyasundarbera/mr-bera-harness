---
type: Decision Record
id: ADR-2026-023
date: 2026-10-14
title: Release 0.2.0 is a minor bump, and the harness has no versioning policy yet
status: Accepted
decision: Release the harness as 0.2.0 by owner decision on the measured basis that nothing was removed and no change declared a break, and record that no versioning policy exists so the next release has no rule to follow; tagging remains undecided.
covers: [MRB]
supersedes: []
---

# Context

`ADR-2026-022` single-sourced the version and recorded that **bumping** it was the owner's
decision, because a release is an owner act. The owner decided: **0.2.0**.

Two questions had to be answered to perform it, and neither had an existing answer:

1. **Is it major, minor or patch?** No semver policy exists anywhere in this repository — no
   `VERSIONING.md`, no statement in `README.md`, `PURPOSE.md` or any ADR. The number could
   not be derived from a rule, so it had to be **justified from evidence** instead.
2. **What does 0.2.0 contain?** `ADR-2026-022` listed *"whether the version should be
   `0.2.0` given the capabilities added since `0.1.0`"* as open without enumerating them.

# Decision

1. **0.2.0, a minor bump**, on this measured basis:

   | Check | Result |
   |---|---|
   | entries by kind | 14 added, 3 changed, 7 fixed |
   | `removed` entries | **none** |
   | `BREAKING CHANGE` footers, excluding merges | **none** |
   | `!` markers in commit subjects | **none** |

   Nothing was removed and no change declared a break, so *minor* states the change
   truthfully. Had any `removed` entry or `BREAKING CHANGE` existed, the same evidence would
   have required a major bump — the basis is evidence, not preference.

2. **The single-source decision paid for itself, and that is recorded.** The bump was one
   line in `src/harness/__init__.py`; the wheel became `mr_bera_harness-0.2.0-py3-none-any.whl`
   with `Version: 0.2.0`, and `--version` reports `harness 0.2.0`. No other file changed. This
   is the first release since `ADR-2026-022` and the first evidence that the arrangement works
   in practice rather than in a probe.

3. **No versioning policy is established, and that is stated rather than implied.** This
   record justifies one number; it does not create a rule. The next release has **no policy
   to follow** and would have to justify itself the same way.

4. **Tagging remains undecided.** The repository has **no git tags**. A tag is what would let
   a consumer pin by tag rather than by 40-hex sha (`ADR-2026-022`; `mr_bera`'s
   `ADR-2026-008`), and it is not performed here.

# Consequences

- **A consumer pin can now be bumped effectively.** `mr_bera` pins `d029f3f`, now behind
  `main` (`f97625a`). While both revisions reported `0.1.0`, a moved pin was **not** honoured
  by an existing environment — measured in `CHG-2026-024`. The version change removes that
  barrier; **the pin bump itself is a separate change in that repository**.
- **The number now means something specific**: all six build-order steps, plus the dashboard,
  the runtime dependency audit, code provenance, and the generated handoff facts.
- **Cost: the absence of a policy is now recorded, not fixed.** The next release is in the
  same position — defensible from evidence, but with no rule to appeal to. That is honest and
  it is a gap.
- **Cost: no tag means consumers still pin a sha**, which is reproducible but not readable —
  `0.2.0` is nowhere in a git ref.

# Remaining the owner's decision

- **Adopt a versioning policy** (semver, or something else) so later releases do not each
  re-derive their basis.
- **Whether to tag `v0.2.0`** — and whether consumers should then pin by tag.
- **When the next release is due**, and whether it is 0.2.1 or 0.3.0.

# Alternatives rejected

- **Bump to 1.0.0.** Major would claim a stable contract, and nothing here asserts one — the
  `Proposed` decisions, the open `ADR-2026-016` defect and the unfixed decision 8 all say the
  contract is still moving.
- **0.1.1 (patch).** Nothing was broken, so a patch bump would understate the change: six
  build-order steps plus four capabilities arrived since `0.1.0`.
- **Bump without recording a basis.** The number would then be unfalsifiable — the exact
  failure `ADR-2026-010` refuses for budget units and `ADR-2026-014` for PostgreSQL versions.
- **Introduce a versioning policy in this change.** A policy is a decision about *all* future
  releases, and folding it into a release would be scope the owner did not ask for. Recorded
  as an option instead.
- **Tag in the same change.** Tagging is a separate, visible act with its own consequences for
  consumers, and this record leaves it to the owner rather than assuming it.
