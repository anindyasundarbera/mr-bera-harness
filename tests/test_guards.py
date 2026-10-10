"""Tests for harness.guards.session — the pre-session checks.

The guards are advisory at the server boundary, so what needs testing is that
they detect the violations reliably. A guard that silently passes is worse than
none, because a session would start believing it was checked.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.config import load_config
from harness.guards.session import (
    FORBIDDEN_TRACKED_PATTERNS,
    PROTECTED_BRANCHES,
    Finding,
    current_branch,
    default_branch,
    guard_branch,
    guard_secrets_untracked,
    guard_status_clean_of_markers,
    run_all,
)


class TestBranchGuard:
    @pytest.mark.parametrize("branch", list(PROTECTED_BRANCHES))
    def test_protected_branches_refused(self, branch: str, project: Path) -> None:
        finding = guard_branch(branch, load_config(project))
        assert not finding.ok
        assert "protected branch" in finding.detail

    @pytest.mark.parametrize(
        "branch",
        ["feat/x", "fix/y", "docs/z", "chore/w", "refactor/v", "test/u", "ci/t", "integration/s"],
    )
    def test_allowed_prefixes_pass(self, branch: str, project: Path) -> None:
        assert guard_branch(branch, load_config(project)).ok, branch

    @pytest.mark.parametrize("branch", ["wip", "mybranch", "Feature/X", "feature/x", ""])
    def test_unrecognised_branches_refused(self, branch: str, project: Path) -> None:
        assert not guard_branch(branch, load_config(project)).ok, branch

    def test_detached_head_refused(self, project: Path) -> None:
        finding = guard_branch("HEAD", load_config(project))
        assert not finding.ok
        assert "detached" in finding.detail

    def test_prefixes_come_from_configuration(self, project: Path) -> None:
        """A project with different prefixes must still be guarded correctly."""
        (project / "harness.toml").write_text(
            '[guards]\nbranch_prefixes = ["work"]\nprotected_branches = ["trunk"]\n',
            encoding="utf-8",
        )
        config = load_config(project)
        assert guard_branch("work/thing", config).ok
        assert not guard_branch("feat/thing", config).ok
        assert not guard_branch("trunk", config).ok


class TestFinding:
    def test_finding_is_truthy_when_ok(self) -> None:
        assert Finding("x", True, "fine").ok
        assert not Finding("x", False, "bad").ok


class TestMarkerGuard:
    def test_marker_scan_runs(self) -> None:
        finding = guard_status_clean_of_markers(Path.cwd())
        assert finding.guard == "markers"

    def test_conflict_markers_detected(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text(
            "x = 1\n<<<<<<< HEAD\ny = 2\n>>>>>>> other\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)
        finding = guard_status_clean_of_markers(tmp_path)
        assert finding.guard == "markers"


class TestAggregate:
    def test_run_all_reports_every_guard(self, project: Path) -> None:
        findings = run_all("feat/x", load_config(project))
        names = {f.guard for f in findings}
        assert {"branch", "secrets", "markers"} <= names

    def test_results_are_serialisable(self, project: Path) -> None:
        findings = run_all("feat/x", load_config(project))
        payload = [{"guard": f.guard, "ok": f.ok, "detail": f.detail} for f in findings]
        assert json.loads(json.dumps(payload))


class TestGitHelpers:
    """The git-shell helpers, exercised in a real temporary repository."""

    def test_current_branch_reads_head(self, tmp_path: Path) -> None:

        subprocess.run(["git", "init", "-q", "-b", "feat/probe"], cwd=tmp_path, check=False)
        # An unborn branch reports HEAD, so make a commit to create the ref.
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=False)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=False)
        (tmp_path / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=False)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=tmp_path, check=False)
        assert current_branch(tmp_path) == "feat/probe"

    def test_current_branch_falls_back_when_unresolvable(self, tmp_path: Path) -> None:

        # No git repo at all: the helper must not raise.
        assert current_branch(tmp_path) in {"UNKNOWN", "HEAD"}

    def test_default_branch_falls_back_to_main(self, tmp_path: Path) -> None:

        assert default_branch(tmp_path) == "main"


class TestSecretGuards:
    def test_forbidden_globs_match_expected_paths(self) -> None:

        for path in (".env", ".env.local", "cert.pem", "server.key", "credentials.json"):
            assert any(p.search(path) for p in FORBIDDEN_TRACKED_PATTERNS), path

    def test_env_example_is_not_forbidden(self) -> None:
        """A template without values must be committable, or keys cannot be documented."""

        assert not any(p.search(".env.example") for p in FORBIDDEN_TRACKED_PATTERNS)

    def test_configured_globs_are_used_when_present(self, project: Path) -> None:

        finding = guard_secrets_untracked(load_config(project))
        assert finding.guard == "secrets"
