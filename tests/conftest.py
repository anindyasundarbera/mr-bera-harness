"""Shared fixtures for the harness test suite.

The harness is project-agnostic, so its tests must be too. Fixtures build a
temporary *consumer project* — a directory with a `harness.toml`, documents,
and a bundle — rather than depending on any one repository's layout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

if os.environ.get("COVERAGE_PROCESS_START"):  # pragma: no cover
    try:
        import coverage

        coverage.process_startup()
    except ImportError:
        pass


HARNESS_TOML = """\
[identity]
name = "TestProject"
id_prefix = "MRB"
levels = ["M", "S", "C", "W", "A"]
widths = [2, 2, 2, 2, 2]

[paths]
docs = "docs"
knowledge = "knowledge"
changelog = "knowledge/changelog"
decisions = "knowledge/decisions"
tests = "tests"
tools = "tools"

[registries.gaps]
path = "docs/GAP_REGISTER.md"
id_column = "Gap ID"
state_column = "State"

[guards]
branch_prefixes = ["feat", "fix", "docs", "chore", "refactor", "test", "ci", "integration"]
protected_branches = ["main", "master"]

[commits]
types = ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"]
"""


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal consumer project with a harness.toml and the standard dirs."""
    root = tmp_path / "project"
    for sub in ("docs", "knowledge/changelog", "knowledge/decisions", "tests", "tools"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "harness.toml").write_text(HARNESS_TOML, encoding="utf-8")
    return root


def write_concept(root: Path, relpath: str, frontmatter: str, body: str = "") -> Path:
    """Create an OKF concept under `root`, creating parents as needed."""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter.strip()}\n---\n\n{body}\n", encoding="utf-8")
    return path


@pytest.fixture
def tmp_bundle(tmp_path: Path) -> Path:
    """An empty OKF bundle root."""
    root = tmp_path / "bundle"
    root.mkdir()
    return root


def git_env() -> dict[str, str]:
    """Environment for test git commands, with an identity supplied explicitly.

    CI runners have no global git identity, so a bare `git commit` fails with
    exit 128 and depends on the host having one configured. Supplying the
    identity here — rather than relying on the machine — is what made these
    fixtures pass locally and fail in CI.
    """
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "Harness Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Harness Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }


def git_run(root: Path, *args: str) -> str:
    """Run a git command in `root`, failing the test loudly on error."""
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False, env=git_env()
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {root}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_commit(root: Path, message: str = "test: fixture") -> str:
    """Stage everything and commit. Returns the new commit's SHA."""
    git_run(root, "add", "-A")
    git_run(root, "commit", "-q", "-m", message)
    return git_run(root, "rev-parse", "HEAD")


def git_commit_all(root: Path, message: str = "test: fixture") -> str:
    """Initialise a repository with a working identity, then commit everything.

    Extraction must be a function of *committed* bytes, so every git-backed test
    fixture has to be a real repository with real commits.
    """
    git_run(root, "init", "-q", "-b", "main")
    # A local identity means a later raw `git commit` in a test still works on a
    # runner with no global one.
    git_run(root, "config", "user.email", "test@example.invalid")
    git_run(root, "config", "user.name", "Harness Test")
    return git_commit(root, message)


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    """A committed consumer project with documents, a bundle and a registry table.

    It is deliberately built from a different layout than the harness's own, so a
    test cannot pass by accidentally reading the harness repository.
    """
    root = tmp_path / "consumer"
    for sub in ("docs", "knowledge/modules", "knowledge/changelog", "tests", "tools"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "harness.toml").write_text(HARNESS_TOML, encoding="utf-8")

    write_concept(
        root,
        "knowledge/modules/M06-engine.md",
        """
type: Module
module: MRB-M06
covers: [MRB-M06]
read_budget: must-read
depends_on: [M06-orchestration]
""",
        "## Purpose\n\nSee [orchestration](M06-orchestration.md).\n",
    )
    write_concept(
        root,
        "knowledge/modules/M06-orchestration.md",
        """
type: Concept
module: MRB-M06
covers: [MRB-M06-S07]
read_budget: reference-only
""",
        "## Contracts\n\nBody.\n",
    )
    write_concept(
        root,
        "knowledge/modules/M06/unknowns/rubric.md",
        """
type: Unknown
module: MRB-M06
covers: [MRB-M06]
blocks: [MRB-M06-S07]
state: BlockedOwner
blocker: DESIGN-RUBRIC-01
read_budget: must-read
if_you_guess: The rubric becomes untestable opinion.
must_not_do:
  - Define a quality threshold.
""",
        "## Why this blocks\n\nThe pass definition is undecided.\n",
    )
    (root / "docs" / "GAP_REGISTER.md").write_text(
        "# Gaps\n\n"
        "| Gap ID | State | Note |\n"
        "|---|---|---|\n"
        "| GAP-CTL-001 | Specified | first |\n"
        "| GAP-FRM-003 | BlockedOwner | second |\n",
        encoding="utf-8",
    )
    git_commit_all(root)
    return root


@pytest.fixture
def pg_conn() -> Iterator[Any]:
    """A live PostgreSQL connection with a fresh, empty index. Skips without one.

    The index layer is derived and optional, so its tests must not be the reason
    CI fails on a machine with no database. They *do* run for real wherever a DSN
    is supplied, which is where the rebuild invariant is actually proven.
    """
    # `MRB_TEST_DSN` only — deliberately no fallback to `MRB_HARNESS_DSN`.
    #
    # The fixtures call `reset`, which drops and recreates the index tables. A
    # fallback meant a suite run against a DSN that also held a real index would
    # destroy it, which is exactly what happened once during development: a test
    # run wiped the indexed consumer project. Requiring a separate, explicitly
    # named test database makes that impossible rather than merely unlikely.
    dsn = os.environ.get("MRB_TEST_DSN")
    if not dsn:
        pytest.skip("no MRB_TEST_DSN; set it to a throwaway database to exercise the store")
    from harness.index.store import (  # noqa: PLC0415 - optional extra, imported on demand
        IndexUnavailableError,
        connect,
        reset,
    )

    try:
        conn = connect(dsn)
    except IndexUnavailableError as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    reset(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _subprocess_coverage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    start = os.environ.get("COVERAGE_PROCESS_START")
    if start:
        monkeypatch.setenv("COVERAGE_PROCESS_START", start)
        monkeypatch.setenv("PYTHONPATH", f"{SRC}{os.pathsep}{REPO_ROOT}")
