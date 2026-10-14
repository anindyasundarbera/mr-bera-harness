---
type: Decision Record
id: ADR-2026-022
date: 2026-10-13
title: The package version is declared once, in the code
status: Accepted
decision: Make harness.__version__ the single source of the package version and derive the distribution metadata from it with setuptools dynamic version, so pyproject.toml no longer restates it and the two cannot drift.
covers: [MRB]
supersedes: []
---

# Context

The version was declared **twice**:

- `pyproject.toml` — `version = "0.1.0"`;
- `src/harness/__init__.py` — `__version__ = "0.1.0"`.

Two copies of one fact, neither checked against the other. This is the same shape as
`CHG-2026-016` (a generated header hardcoding a path it should have read) and
`CHG-2026-020` (a README asserting a gap four hours after it closed): a second copy with
nothing reconciling it.

It became load-bearing when the consumer pinned the harness to an exact commit
(`mr_bera`'s `ADR-2026-008`). That fix surfaced a concrete consequence: **pip compares
versions, not refs**, so a consumer whose pin moved to a different commit that still
reported `0.1.0` was **not** upgraded — measured, `pip install -e .` left a 16-file
installation untouched while the pinned revision had 45 files. A version that cannot
change when the code does is not a version.

The code has to carry the value regardless: `harness --version` and the dashboard's
provenance record both read `harness.__version__`.

# Decision

1. **`harness.__version__` is the single source.**
2. **`pyproject.toml` declares it as dynamic**, with
   `[tool.setuptools.dynamic] version = { attr = "harness.__version__" }`, so the
   distribution metadata is *derived* from the module rather than restated beside it.
3. **A test asserts the arrangement's structure, not a value.**
   `tests/test_version_single_source.py` requires that `pyproject.toml` has **no** static
   `version`, that `version` appears in `dynamic`, that the source is exactly
   `harness.__version__`, and that the **installed distribution metadata equals the code**
   — the end-to-end check that would have caught the original defect.

   This matters: a test that merely compared the two strings would pass while *both
   copies remained*. The defect is the existence of the second declaration, so the test
   asserts its absence.

4. **A skip states what was not checked.** When the distribution is not installed the
   metadata comparison skips with a reason, rather than passing silently.

# Consequences

- **One place to change the version.** Bumping it is a one-line edit, and it cannot
  disagree with itself.
- **Proven, not asserted.** Changing `harness.__version__` to `9.9.9` produced a wheel
  named `mr_bera_harness-9.9.9-py3-none-any.whl` whose metadata read `Version: 9.9.9` —
  the derivation is real, not a coincidence of equal strings. Restoring the value restored
  `0.1.0`.
- **The built artifact is unchanged** for `0.1.0`: `Name: mr-bera-harness`,
  `Version: 0.1.0`.
- **The consumer's bump problem is now addressable**, though not solved here: a bump can
  now change the reported version, which is the precondition for pip to honour a moved
  pin. Whether to bump, and to what, remains the owner's.
- Cost: the version now lives in code that is imported at build time. That is the intent —
  the alternative is the second copy — but it means a syntax error in `__init__.py` fails
  the build earlier than it otherwise would.
- **A build artifact from a probe was found by this very test.** A stale
  `src/mr_bera_harness.egg-info/PKG-INFO` left by an experiment reported `9.9.9` while the
  code said `0.1.0`, and `test_the_installed_metadata_matches_the_code` failed on it. It
  was `*.egg-info/` (gitignored) and cleaned, but the episode is recorded because it is
  evidence the check detects **real** drift rather than a difference in text.

# Remaining the owner's decision

- **Whether to bump the version now.** The consumer's pin can only take effect for an
  existing environment if the version changes, so this is the natural next step — but it
  is a release act, and this record does not perform one.
- **Whether to tag `v0.1.0` and have consumers pin by tag.** Cross-repo, and it depends on
  this single-sourcing landing first.
- **Whether the version should be `0.2.0`** given the capabilities added since `0.1.0`.

# Alternatives rejected

- **Leave both declarations and add an equality test.** Passes while both copies remain;
  the drift needs one copy removed, not compared.
- **Single-source from `pyproject.toml` instead**, reading it in `__init__.py`. It would
  make an installed package parse a file that is **not shipped in the wheel** (verified:
  the wheel contains only `harness/` and the dist-info), so `harness.__version__` would
  fail or need a fallback — a second path to maintain.
- **Keep the version only in `pyproject.toml` and drop `__version__`.** `--version` and the
  dashboard read the module attribute, so they would need `importlib.metadata` and a
  fallback when the distribution is absent (an editable checkout, a vendored copy) —
  more machinery for the same fact.
- **A `VERSION` file read by both.** A third artifact, and still two readers to keep wired.
