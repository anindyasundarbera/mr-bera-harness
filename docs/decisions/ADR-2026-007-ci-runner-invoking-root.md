---
type: Decision Record
id: ADR-2026-007
date: 2026-10-13
title: The local CI runner resolves the invoking repository, not the package directory
status: Accepted
decision: Make harness ci execute its stages in the invoking repository (Path.cwd) and make the parity check read the workflow file, closing the last location-resolved-from-the-library defect in the harness.
covers: [MRB]
supersedes: []
---

# Context

`ci/rehearse.py` still derived its root from its own location —
`Path(__file__).resolve().parent.parent` — which resolves to the *installed
package* directory (`.../src/harness`). Its siblings had already been corrected
(`guards/session.py`, `entries/commits.py`, `entries/generator.py`); the runner
was missed.

Because `ADR-2026-003` and the repository's own instructions make
`harness ci` the rehearsal a session must run before pushing, the defect was in
the one instrument the process trusts.

Observed on the unfixed tree, from the harness repository root:

```
$ harness ci --workflow .github/workflows/ci.yml
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  mypy --strict      Cannot read file: tools: No such file or directory
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
  ... (8 of 12 steps failed)
[parity] local stages vs .github/workflows/ci.yml
  missing locally: none      <-- reported success while reading nothing
RESULT: FAILED
```

Two distinct faults were exposed: the stages ran in the wrong directory, and the
parity check compared the pipeline against a list it had not actually parsed, so
it asserted success vacuously. The stage definitions also named `tools/*.py`,
which no longer exists, and `mypy tools`, which `ci.yml` does not use.

# Decision

1. `repo_root()` resolves `Path.cwd()` (or an explicit root), matching
   `guards/session.py`. `run_stage` runs there.
2. `check_parity` reads the workflow file. `cmd_ci` uses it for `--workflow`, and
   a parity failure fails the run rather than printing a note.
3. The `selfcheck` stages call existing commands — `harness entries generate
   --check`, `harness context`, `harness doctor` — and `mypy src` matches
   `ci.yml`. The **session** guards are deliberately *not* a stage: they refuse a
   protected branch (ADR-2026-004), so a stage invoking them fails on `main` by
   definition, and would fail CI on every push to the default branch. See
   ADR-2026-008.
4. `Step.ok_exit_codes` records that a deliberate non-zero result is a passing
   check: `harness context` exits 3 or 4 *by design*, so a rehearsal that
   insisted on 0 could not assert the exit-code contract.

# Consequences

- The rehearsal now exercises the real pipeline: from 8 failures to
  `RESULT: PASSED`, with `parity: every CI job has a local stage`.
- Regression tests pin the root and the parity read, so the defect cannot return
  silently.
- A consequence found while fixing it: with the runner correctly executing in the
  invoking repository, a test that called `main(["ci"])` from inside pytest
  recursed forever, because the `test` stage runs pytest. The test now composes a
  trivial pipeline through the module's own `Stage`/`Step` types and asserts the
  runner drives it — a test of the wiring, without re-entering the suite.
- Cost: a stage's working directory is now a real input, so the harness is no
  longer usable with an implicit root. That is the intended trade — an implicit
  root is what produced the wrong one.

# Alternatives rejected

- **Keep the package-relative root and set `cwd` per step from `config.root`.**
  Rejected as cosmetic: leaving a wrong root reachable keeps the defect alive,
  and `config.root` is already `Path.cwd()` for the CLI.
- **Leave the parity check as a printed note.** Rejected: it reported success
  while having read nothing, which is worse than no check.
- **Skip the selfcheck stages entirely.** Rejected: it would hide the dead `tools/`
  paths rather than remove them.
