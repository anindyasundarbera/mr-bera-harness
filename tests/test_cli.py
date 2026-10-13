"""Tests for harness.cli — the single entry point.

Every subcommand must be reachable and must return a documented exit code, because
`AGENTS.md` tells agents to run these and a missing subcommand would silently do
nothing — which is how the guards were once dropped from the CLI entirely.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness.cli import build_parser, main


def subcommands() -> set[str]:
    parser = build_parser()
    action = next(a for a in parser._actions if getattr(a, "choices", None))
    return set(action.choices)  # type: ignore[attr-defined]


class TestSubcommandCoverage:
    """Every capability the documentation mentions must be reachable."""

    EXPECTED = {
        "describe",
        "context",
        "conform",
        "guards",
        "commits",
        "entries",
        "ci",
        "index",
        "doctor",
    }

    def test_all_subcommands_registered(self) -> None:
        assert subcommands() >= self.EXPECTED

    def test_no_unexpected_subcommands(self) -> None:
        assert subcommands() <= self.EXPECTED, "an undocumented subcommand appeared"

    def test_guards_is_reachable(self) -> None:
        """The guards were once removed from the CLI and nothing failed.

        `AGENTS.md` instructs agents to run them, so their absence would have
        been silent.
        """
        assert "guards" in subcommands()


class TestDescribeAndConform:
    def test_describe_succeeds(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(project)
        assert main(["describe"]) == 0

    def test_conform_succeeds(self, project: Path) -> None:
        assert main(["--root", str(project), "conform"]) == 0

    def test_describe_without_config_errors(self, tmp_path: Path) -> None:
        assert main(["--root", str(tmp_path), "describe"]) == 2


class TestGuards:
    def test_guards_runs(self, project: Path) -> None:
        assert main(["--root", str(project), "guards", "--branch", "feat/x"]) in {0, 1}

    def test_guards_json_is_parseable(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["--root", str(project), "guards", "--branch", "feat/x", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert "passed" in payload
        assert isinstance(payload["findings"], list)

    def test_protected_branch_fails(self, project: Path) -> None:
        assert main(["--root", str(project), "guards", "--branch", "main"]) == 1


class TestContext:
    def test_uncovered_chain_is_four(self, project: Path) -> None:
        assert main(["--root", str(project), "context", "MRB-M06-S07"]) == 4

    def test_bad_identifier_is_two(self, project: Path) -> None:
        assert main(["--root", str(project), "context", "NOT-AN-ID"]) == 2

    def test_json_is_parseable(self, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main(["--root", str(project), "context", "MRB-M06", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["work_id"] == "MRB-M06"
        assert payload["chain"] == ["MRB-M06"]


class TestCommits:
    def test_message_accepts(self) -> None:
        assert main(["commits", "--message", "feat: add a thing"]) == 0

    def test_message_rejects(self) -> None:
        assert main(["commits", "--message", "nope"]) == 1

    def test_unresolvable_range_is_two(self) -> None:
        assert main(["commits", "nonexistent-ref-xyz..HEAD"]) == 2


class TestEntries:
    def test_validate_runs(self, project: Path) -> None:
        assert main(["--root", str(project), "entries", "validate"]) == 0

    def test_generate_writes_to_the_invoking_project(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generated files belong to the project that ran the command.

        An earlier version derived the output path from the harness package's own
        location, so running this inside a consumer wrote into the *harness*
        repository — silently modifying a different project.
        """
        monkeypatch.chdir(project)
        assert main(["entries", "generate"]) == 0
        assert (project / "CHANGELOG.md").exists()
        assert (project / "docs" / "DECISIONS_INDEX.md").exists()

    def test_generate_check_passes_once_generated(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        assert main(["entries", "generate"]) == 0
        assert main(["entries", "generate", "--check"]) == 0

    def test_generate_without_subcommand_is_usage_error(self) -> None:
        with pytest.raises(SystemExit):
            main(["entries"])


class TestCi:
    def test_ci_runs_the_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exercises the rehearsal runner without recursively running this suite.

        `harness ci`'s own `test` stage invokes pytest. Now that the runner
        correctly executes in the invoking repository, running the full default
        pipeline from inside pytest would recurse forever. A trivial pipeline
        proves the CLI drives stages and reports their result, which is what this
        test is for; `test_ci.py` covers the real stage definitions.
        """
        from harness.ci import rehearse  # noqa: PLC0415 - imported only for this test

        trivial = rehearse.Pipeline(
            stages=[
                rehearse.Stage(
                    "lint",
                    "trivial",
                    [rehearse.Step("true", [sys.executable, "-c", "pass"])],
                )
            ]
        )
        monkeypatch.setattr(rehearse, "default_pipeline", lambda: trivial)
        assert main(["ci"]) == 0

    def test_ci_reports_a_failing_stage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from harness.ci import rehearse  # noqa: PLC0415 - imported only for this test

        failing = rehearse.Pipeline(
            stages=[
                rehearse.Stage(
                    "lint",
                    "always fails",
                    [rehearse.Step("false", [sys.executable, "-c", "raise SystemExit(1)"])],
                )
            ]
        )
        monkeypatch.setattr(rehearse, "default_pipeline", lambda: failing)
        assert main(["ci"]) == 1

    def test_ci_runs_stages_in_the_invoking_repository(self, project: Path) -> None:
        """A stage's working directory is the project, never the package install."""
        from harness.ci import rehearse  # noqa: PLC0415 - imported only for this test

        assert rehearse.repo_root(project) == project.resolve()
        assert rehearse.repo_root() != Path(rehearse.__file__).resolve().parent


class TestDoctor:
    def test_doctor_reports_clean_on_a_valid_project(self, project: Path) -> None:
        assert main(["--root", str(project), "doctor"]) == 0

    def test_doctor_without_config_errors(self, tmp_path: Path) -> None:
        assert main(["--root", str(tmp_path), "doctor"]) == 2


class TestTopLevel:
    def test_no_command_is_usage_error(self) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_version_is_available(self) -> None:
        with pytest.raises(SystemExit):
            main(["--version"])
