"""Shared fixtures for the harness test suite.

The harness is project-agnostic, so its tests must be too. Fixtures build a
temporary *consumer project* — a directory with a `harness.toml`, documents,
and a bundle — rather than depending on any one repository's layout.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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


@pytest.fixture(autouse=True)
def _subprocess_coverage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    start = os.environ.get("COVERAGE_PROCESS_START")
    if start:
        monkeypatch.setenv("COVERAGE_PROCESS_START", start)
        monkeypatch.setenv("PYTHONPATH", f"{SRC}{os.pathsep}{REPO_ROOT}")
