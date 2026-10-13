---
type: Changelog Entry
id: CHG-2026-006
date: 2026-10-13
kind: fixed
title: The local CI rehearsal runs in the invoking repository again
summary: harness ci resolved its root from the installed package directory, so 8 of 12 stages failed while its parity check reported success having read nothing; stages now run in the invoking repository and parity reads the workflow.
covers: [MRB]
---

`ci/rehearse.py` was the last module still resolving its own location
(`Path(__file__).resolve().parent.parent`), which points at the installed package
(`.../src/harness`) rather than the repository the command was run in. Its
siblings had already been corrected; the runner was missed.

## Observed, before the fix

From the harness repository root:

```
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
[parity] local stages vs .github/workflows/ci.yml
  missing locally: none      <-- reported success while reading nothing
RESULT: FAILED — package, typecheck, test, selfcheck
```

Eight of twelve steps failed. The parity check was the worse fault: it compared
the pipeline against a job list it had not parsed, so a green local run would
have meant nothing.

## Fixed

- `repo_root()` resolves `Path.cwd()`, matching `guards/session.py`;
  `run_stage` executes there.
- `check_parity` reads the workflow file, and a parity failure now fails the run.
- The `selfcheck` stages name existing commands; `mypy src` matches `ci.yml`; the
  dead `tools/*.py` references are gone.
- `Step.ok_exit_codes` records that a deliberate non-zero exit is a passing
  check, so the rehearsal can assert the `harness context` exit-code contract.

Result: `RESULT: PASSED`, `parity: every CI job has a local stage`.

## Found while fixing it

With the runner correctly executing in the invoking repository, a test that
called `main(["ci"])` from inside pytest recursed forever — the `test` stage runs
pytest. The test now builds a trivial pipeline from the module's own stages and
asserts the runner drives it, without re-entering the suite.

**Tests:** regression tests pin the root and the parity read.
