---
type: Changelog Entry
id: CHG-2026-021
date: 2026-10-13
kind: added
title: The handoff's facts are generated, so they stop going stale
summary: Split docs/design/REMAINING_WORK.md into hand-written narrative and a marker-delimited region refreshed by tools/refresh_handoff.py from the harness's own derivations, with a --check mode that exits 1 on staleness; the region holds only facts that are functions of the committed content.
covers: [MRB]
---

The handoff is the first document a new session is told to trust, and it has already
been wrong once — the v2.0 refresh found it describing steps 1–3 as the state and steps
4–6 as "not started" when all six were merged. That was fixed by rewriting it. The
*facts* that were wrong are the kind a machine knows exactly, and they had been
refreshed by hand, so they were due to decay again the moment the next change landed.

## What changed

`docs/design/REMAINING_WORK.md` now carries a generated region delimited by
`<!-- harness:handoff-facts:start/end -->`. `tools/refresh_handoff.py` fills it with
values **derived** from the repository through the harness's own library:

| Fact | Derived from |
|---|---|
| OKF concepts | the `Bundle` reader |
| entries, problems | the entries `validate_all` |
| test modules | the configured tests directory |
| provenance declarations | the provenance `check` |
| commit vocabulary | the resolved `Config` |

Nothing is re-implemented. A second implementation would be a second definition of "the
entry count", and the two would drift — the defect, reintroduced in the fix.

## The design decision that came from building it

The first implementation also rendered **the revision** and **the test pass/skip
counts**. Both were removed, and the reason is worth recording because it was found by
observation rather than by reasoning ahead:

- **A committed file cannot contain its own commit's hash.** A region stating
  `Revision: <HEAD>` is stale the instant it is committed, so `--check` could never
  return `0` and the scheduled job would rewrite the same lines forever.
- **The test counts describe the environment.** The same commit reports one pair without
  a database and a different pair with one, so the check would differ between a laptop
  and CI — the class of defect already paid for twice here (a coverage floor measured
  differently with and without `MRB_TEST_DSN`).

The rule, stated once: **the region holds only facts that are functions of the committed
content.** A fact about the checkout or the machine is not a fact about the repository.
The rule is pinned by a test that asserts the `Facts` dataclass carries none of those
fields, so re-adding one fails with the reason attached.

## What deliberately did not change

**The narrative.** What was built, what is blocked, what is next is a judgement; a
script that produced it would be inventing a handoff. Only the marked region is
generated, and the splice is tested to leave every byte outside it untouched.

## The interface

```
refresh_handoff.py            # refresh the region (exit 0)
refresh_handoff.py --check    # exit 1 if stale, 2 if the handoff has no markers
```

The `1` is what a scheduled job acts on without mutating anything. A handoff with no
markers exits `2` rather than doing nothing quietly — a silent no-op would report
success while refreshing nothing.

## Proven, not asserted

- Tampering with a derived value (`OKF concepts 21` → `20`) made `--check` exit **1**;
  the refresher restored it and `--check` returned **0**.
- **The region settles on a committed tree.** `--check` returns `0` after a real commit,
  which the first design could not have achieved by construction.

**Stated limit:** the script proves the region matches the repository's derivations. It
cannot prove the narrative is true — the v1.0 staleness was prose, and no marker catches
prose.

**Tests:** 624 without a database (18 new); coverage 82.2%. Lint, format,
`mypy --strict`, `harness doctor`, `harness provenance check` and `harness ci` all clean.
