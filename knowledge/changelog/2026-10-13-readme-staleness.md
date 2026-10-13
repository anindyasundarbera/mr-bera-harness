---
type: Changelog Entry
id: CHG-2026-020
date: 2026-10-13
kind: fixed
title: The README no longer claims a gap the repository has closed
summary: PR #15 implemented code provenance and updated PURPOSE.md to say the gap was closed, but did not touch the README, which links PURPOSE.md and had claimed the same gap was open in two places; a broken architecture path and an undocumented command were fixed in the same pass, and a test now checks README links resolve.
covers: [MRB]
---

The same class of defect `CHG-2026-016` fixed in the generated header — a document
asserting something the repository no longer makes true — reappeared one file over,
because the change that closed the gap updated `docs/PURPOSE.md` and every design
note it owns, but not the README that links to it.

## Three contradictions, all in one file

1. **A closed gap still described as open, twice.** `README.md:19` said
   *"including the one gap it does not yet close: there is no checked link from a
   line of code to the decision that produced it"* and `README.md:154` repeated it.
   `PURPOSE.md` §4 now says the opposite — *"Recently closed — the gap this document
   previously named as the principal one"* — and `harness provenance check` exits 0.
   The README therefore **contradicted the document it links to**, which is the
   drift this repository exists to catch.
2. **A broken internal path.** `README.md:134` pointed at
   `docs/HARNESS_ARCHITECTURE.md`; the file is `docs/design/HARNESS_ARCHITECTURE.md`.
   Line 143 of the same file already had it right.
3. **An undocumented shipped command.** The Status section said *"All six build-order
   components are implemented"* while `harness provenance` — built beyond the build
   order — appeared nowhere in the README, unlike every other command group.

## The fix, and the check that stops the recurrence

The two false claims are replaced with wording that does not overclaim, the path
becomes `docs/design/`, and the provenance commands join the command list.

The larger point is that nothing caught this: no test read the README, and
`harness doctor` does not. `tests/test_readme.py` now checks that every relative link
in the README resolves to a tracked file, so a moved or misspelled path fails the
suite rather than a reader.

Stated plainly: the test checks that a link **resolves**, not that its *target is
still true*. Claim 1 above — a document asserting a stale fact — is not machine-checkable
from a link, and this test does not pretend otherwise. What it removes is the class
where the README points at a file that is not there.

**Tests:** 606 without a database (6 new); coverage unchanged at 82.2%. Lint, format,
`mypy --strict`, `harness doctor` and `harness ci` all clean.
