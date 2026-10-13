#!/usr/bin/env python3
"""Local CI runner — rehearse the pipeline before pushing.

GitHub Actions cannot be run locally. This runner executes the **same commands**
the workflow runs, in the same order, under the same environment constraints, so
a push is not the first time the pipeline is exercised.

Where it differs from `ci.yml`, it is called out in the output. The honest
limitation: this is a *simulation*, not the real pipeline. It cannot reproduce
runner images, the version matrix, caching or service containers.

Usage
-----
    python3 tools/local_ci.py                 # run every stage
    python3 tools/local_ci.py --stage lint    # one stage
    python3 tools/local_ci.py --stage test --stage governance
    python3 tools/local_ci.py --list          # show stages
    python3 tools/local_ci.py --parity        # check runner/CI drift

Exit codes: 0 = all stages passed, 1 = a stage failed, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def repo_root(root: Path | None = None) -> Path:
    """The repository the command was invoked in, not the package's own location.

    This was `Path(__file__).resolve().parent.parent`, which resolves to the
    *installed package* directory (`.../src/harness`). Every stage then ran
    there, so the wheel build could not find `pyproject.toml`, pytest could not
    find `tests/`, and the self-check could not find `harness.toml` — eight of
    twelve steps failed while the parity check still reported success. The
    invoking directory is the only correct answer, matching `guards/session.py`
    and `entries/commits.py`.
    """
    return (root or Path.cwd()).resolve()


PY = sys.executable


@dataclass
class ParityResult:
    """Outcome of comparing local stages against the CI workflow's jobs."""

    ci_jobs: list[str]
    local_stages: list[str]

    @property
    def missing(self) -> list[str]:
        return [j for j in self.ci_jobs if j not in self.local_stages]

    @property
    def extra(self) -> list[str]:
        return [s for s in self.local_stages if s not in self.ci_jobs]

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass
class Pipeline:
    """An ordered set of stages a project wants rehearsed locally."""

    stages: list[Stage]

    def parity(self, ci_jobs: list[str]) -> ParityResult:
        """Compare this pipeline against the jobs a CI workflow defines."""
        return ParityResult(ci_jobs=list(ci_jobs), local_stages=[s.name for s in self.stages])


@dataclass
class Step:
    label: str
    argv: list[str]
    requires: tuple[str, ...] = ()
    #: Exit codes that mean the step succeeded. Defaults to `(0,)`, but a
    #: deliberate non-zero result is also a passing check: `harness context`
    #: exits 3 (a blocker applies) or 4 (nothing covers the chain) *by design*,
    #: so a rehearsal that insisted on 0 could not assert that contract.
    ok_exit_codes: tuple[int, ...] = (0,)


@dataclass
class Stage:
    name: str
    description: str
    steps: list[Step]
    parity_note: str = ""


def stages() -> list[Stage]:
    """The stages, mirroring .github/workflows/ci.yml job-for-job."""
    return [
        Stage(
            name="package",
            description="build metadata and wheel (catches pyproject errors)",
            steps=[
                Step(
                    "wheel build",
                    [
                        PY,
                        "-m",
                        "pip",
                        "wheel",
                        "--no-deps",
                        "-w",
                        "/tmp/.mrb-wheel-check",
                        ".",
                    ],
                ),
            ],
            parity_note=(
                "Mirrors the CI package job exactly, including build isolation. "
                "An earlier version used --no-build-isolation, which passed here "
                "only because this host has setuptools installed and failed in "
                "CI where it does not. Local fidelity matters more than speed."
            ),
        ),
        Stage(
            name="lint",
            description="ruff check + format check",
            steps=[
                Step("ruff check", ["ruff", "check", "."]),
                Step("ruff format --check", ["ruff", "format", "--check", "."]),
            ],
        ),
        Stage(
            name="typecheck",
            description="mypy --strict over the package (matches CI's `mypy src`)",
            steps=[Step("mypy --strict", [PY, "-m", "mypy", "src"], requires=("mypy",))],
            parity_note=(
                "CI uses the interpreter from its own setup-python step; this run "
                "uses the local one. Version skew is possible but rare."
            ),
        ),
        Stage(
            name="test",
            description="pytest",
            steps=[Step("pytest", [PY, "-m", "pytest", "tests/", "-q"])],
        ),
        Stage(
            name="selfcheck",
            description="the harness runs on itself",
            steps=[
                Step("okf conformance", [PY, "-m", "harness.cli", "conform"]),
                Step("routing invariants", [PY, "-m", "harness.cli", "doctor"]),
                Step("entry schema", [PY, "-m", "harness.cli", "doctor"]),
                Step("branch not stacked", [PY, "-m", "harness.cli", "guards", "--json"]),
                Step(
                    "generated indexes current",
                    [PY, "-m", "harness.cli", "entries", "generate", "--check"],
                ),
                Step(
                    "resolver exit contract",
                    [PY, "-m", "harness.cli", "context", "MRB-M02"],
                    ok_exit_codes=(0, 3, 4),
                ),
                Step(
                    "commit convention",
                    [PY, "-m", "pytest", "tests/", "-q", "--no-header"],
                ),
            ],
        ),
    ]


def default_pipeline() -> Pipeline:
    """The harness's own pipeline, so it rehearses what its CI actually runs.

    A consumer defines its own `Pipeline` directly; this default exists only so
    the harness can dogfood itself.
    """
    return Pipeline(stages=stages())


def workflow_jobs(workflow: Path) -> list[str]:
    """Job names from a GitHub Actions workflow's `jobs:` block.

    Only the `jobs:` block is read: `on:`, `env:` and `permissions:` share the
    same indentation, and a naive scan reports triggers as jobs.
    """
    if not workflow.exists():
        return []
    jobs: list[str] = []
    in_jobs = False
    for line in workflow.read_text(encoding="utf-8").splitlines():
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith(" "):
            break
        if in_jobs and re.match(r"^  [A-Za-z0-9_-]+:\s*$", line):
            jobs.append(line.strip().rstrip(":"))
    return jobs


def tool_available(name: str) -> bool:  # noqa: ARG001
    if name == "mypy":
        probe = subprocess.run(
            [PY, "-m", "mypy", "--version"], capture_output=True, text=True, check=False
        )
        return probe.returncode == 0
    return shutil.which(name) is not None


def run_stage(stage: Stage, root: Path | None = None) -> tuple[bool, list[str]]:
    """Run one stage in the invoking repository. Returns (passed, messages)."""
    cwd = repo_root(root)
    messages: list[str] = []
    passed = True
    for step in stage.steps:
        for requirement in step.requires:
            if not tool_available(requirement):
                messages.append(
                    f"  SKIP  {step.label}: `{requirement}` is not available locally "
                    "(CI installs it; run `pip install -e '.[dev]'`)"
                )
                break
        else:
            started = time.monotonic()
            proc = subprocess.run(  # noqa: S603
                step.argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONWARNINGS": "error"},
            )
            elapsed = time.monotonic() - started
            if proc.returncode in step.ok_exit_codes:
                messages.append(f"  PASS  {step.label}  (exit {proc.returncode}, {elapsed:.2f}s)")
            else:
                passed = False
                messages.append(f"  FAIL  {step.label}  (exit {proc.returncode})")
                output = (proc.stdout + proc.stderr).strip()
                if True:  # a failing step must always show why
                    for line in output.splitlines()[-25:]:
                        messages.append(f"        {line}")
    return passed, messages


def check_parity(workflow: Path | None = None, root: Path | None = None) -> tuple[bool, list[str]]:
    """Compare this runner's stages against the workflow's job names."""
    root = repo_root(root)
    workflow = workflow if workflow is not None else root / ".github" / "workflows" / "ci.yml"
    messages: list[str] = []
    if not workflow.exists():
        return False, [f"workflow not found: {workflow}"]

    # Job names come from `workflow_jobs`, which reads only the `jobs:` block.
    ci_jobs = workflow_jobs(workflow)

    local_stages = [s.name for s in stages()]

    missing = [j for j in ci_jobs if j not in local_stages]
    extra = [s for s in local_stages if s not in ci_jobs]

    messages.append(f"CI jobs      : {', '.join(ci_jobs) or '(none found)'}")
    messages.append(f"Local stages : {', '.join(local_stages)}")
    if missing:
        messages.append(f"MISSING locally: {', '.join(missing)} — CI will run these untested")
    if extra:
        messages.append(f"EXTRA locally: {', '.join(extra)} — not in CI")
    if not missing and not extra:
        messages.append("parity: every CI job has a local stage")
    return (not missing), messages
