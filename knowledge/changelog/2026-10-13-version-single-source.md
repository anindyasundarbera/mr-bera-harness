---
type: Changelog Entry
id: CHG-2026-024
date: 2026-10-13
kind: fixed
title: The package version is declared once, in the code
summary: Removed the second version declaration from pyproject.toml and derived the distribution metadata from harness.__version__ via setuptools dynamic version, so the two cannot drift; proven by changing the code and observing the wheel follow, and a test asserts the arrangement's structure rather than comparing two strings.
covers: [MRB]
---

The version was declared twice — `pyproject.toml` and `src/harness/__init__.py` — so the
two could disagree, and nothing compared them. Same shape as `CHG-2026-016` (a header
hardcoding a path) and `CHG-2026-020` (a README asserting a closed gap): a second copy
with nothing reconciling it.

## Why it became load-bearing, not cosmetic

The consumer pinned the harness to an exact commit (`mr_bera` `ADR-2026-008`), and that fix
surfaced a concrete consequence: **pip compares versions, not refs**. A consumer whose pin
moved to a different commit that still reported `0.1.0` was **not** upgraded — measured,
`pip install -e .` left a 16-file installation untouched while the pinned revision had 45.
A version that cannot change when the code does is not a version.

## What changed

- `pyproject.toml` no longer declares a static `version`; it lists `version` under
  `dynamic` and sources it with
  `[tool.setuptools.dynamic] version = { attr = "harness.__version__" }`.
- The code stays the source, because it has to carry the value regardless: `harness
  --version` and the dashboard's provenance record both read `harness.__version__`.
- `tests/test_version_single_source.py` (6 tests) asserts the **absence** of a second
  declaration, that the dynamic source is exactly `harness.__version__`, and that the
  **installed metadata equals the code**.

## Proven, not asserted

Setting `harness.__version__ = "9.9.9"` produced `mr_bera_harness-9.9.9-py3-none-any.whl`
with `Version: 9.9.9` in its metadata. Restoring it restored `0.1.0`, and the built
artifact for `0.1.0` is unchanged.

**And the test found real drift during this work.** A stale
`src/mr_bera_harness.egg-info/PKG-INFO` left by the experiment reported `9.9.9` while the
code said `0.1.0`, and `test_the_installed_metadata_matches_the_code` failed on it — which
is evidence the check detects actual drift rather than a difference in text. The artifact
was gitignored and cleaned.

**Why the test asserts structure rather than equality:** comparing two strings would pass
while *both* copies remained. The defect is the existence of the second declaration, so the
test asserts its absence.

**Not done here:** bumping the version, and tagging. Both are release acts and are recorded
in `ADR-2026-022` as the owner's.

**Tests:** 630 without a database; coverage 82%. `harness doctor` clean (44 entries, 0
problems), `harness provenance check` exit 0, `refresh_handoff.py --check` exit 0.
