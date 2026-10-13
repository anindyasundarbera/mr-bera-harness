"""Tests for harness.cli — the single entry point.

Every subcommand must be reachable and must return a documented exit code, because
`AGENTS.md` tells agents to run these and a missing subcommand would silently do
nothing — which is how the guards were once dropped from the CLI entirely.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.conftest import HARNESS_TOML, git_commit_all, write_concept

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
        "query",
        "compile",
        "dashboard",
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


class TestQuery:
    """`harness query` must be reachable and must not invent an answer.

    Without a DSN it exits 3 — the derived store is unreachable — rather than
    reporting "nothing applies", which would be a lie an agent could act on.
    """

    def test_query_without_dsn_is_three(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        assert main(["query", "documents"]) == 3

    def test_query_without_dsn_explains_itself(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        main(["query", "blocked", "MRB-M06"])
        err = capsys.readouterr().err
        assert "MRB_HARNESS_DSN" in err

    def test_unknown_field_is_a_usage_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The field name is validated before any connection is attempted.

        A usage error must not depend on a database being reachable, or the
        message a user gets is about the wrong problem.
        """
        monkeypatch.chdir(project)
        monkeypatch.setenv("MRB_HARNESS_DSN", "postgresql://postgres@127.0.0.1:1/none")
        assert main(["query", "touching", "MRB-M06", "--field", "title"]) == 2

    def test_bad_direction_is_rejected_by_the_parser(self) -> None:
        """`--direction` is constrained by argparse, so it never reaches a query."""
        with pytest.raises(SystemExit):
            main(["query", "links", "x", "--direction", "sideways"])


class TestQueryCommandsReachTheEngine:
    """Each query subcommand must be wired, and must answer from the index.

    A subcommand that silently did nothing would be worse than a missing one,
    because an agent would read "no results" as a fact.
    """

    @pytest.fixture
    def indexed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
        """A tiny indexed consumer project, reachable through the real CLI path."""
        root = tmp_path / "consumer"
        for sub in ("docs", "knowledge/modules", "tests", "tools"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        (root / "harness.toml").write_text(HARNESS_TOML, encoding="utf-8")
        write_concept(
            root,
            "knowledge/modules/M06.md",
            "type: Module\nmodule: MRB-M06\ncovers: [MRB-M06]\nread_budget: must-read",
            "## Purpose\n\nBody.\n",
        )
        git_commit_all(root)

        dsn = os.environ.get("MRB_TEST_DSN")
        if not dsn:
            pytest.skip("no MRB_TEST_DSN")
        from harness.config import load_config  # noqa: PLC0415 - only this fixture needs it
        from harness.extract.source import model_from_git  # noqa: PLC0415
        from harness.index.store import (  # noqa: PLC0415
            IndexUnavailableError,
            connect,
            reset,
            write_model,
        )

        try:
            conn = connect(dsn)
        except IndexUnavailableError as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"PostgreSQL unavailable: {exc}")
        reset(conn)
        write_model(conn, model_from_git(root, load_config(root)))
        conn.close()

        monkeypatch.chdir(root)
        monkeypatch.setenv("MRB_HARNESS_DSN", dsn)
        yield root

    def test_documents_returns_rows(
        self, indexed: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["query", "documents"]) == 0
        assert "modules/M06" in capsys.readouterr().out

    def test_json_output_is_parseable(
        self, indexed: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["query", "documents", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["concept_id"] == "modules/M06"

    def test_show_returns_one_document(
        self, indexed: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["query", "show", "modules/M06"]) == 0
        assert "M06" in capsys.readouterr().out

    def test_show_missing_is_one(self, indexed: Path) -> None:
        assert main(["query", "show", "nope/nothing"]) == 1

    def test_search_finds_it(self, indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["query", "search", "M06"]) == 0
        assert "modules/M06" in capsys.readouterr().out

    def test_links_runs(self, indexed: Path) -> None:
        assert main(["query", "links", "modules/M06"]) == 0

    def test_touching_finds_the_scope(
        self, indexed: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["query", "touching", "MRB-M06"]) == 0
        assert "modules/M06" in capsys.readouterr().out

    def test_blocked_runs_and_reports_none(
        self, indexed: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["query", "blocked", "MRB-M06"]) == 0
        assert "no stop conditions" in capsys.readouterr().out

    def test_stops_runs(self, indexed: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["query", "stops"]) == 0
        assert "no stop conditions" in capsys.readouterr().out

    def test_decisions_runs(self, indexed: Path) -> None:
        assert main(["query", "decisions"]) == 0

    def test_gaps_runs(self, indexed: Path) -> None:
        assert main(["query", "gaps"]) == 0


class TestCompile:
    """`harness compile` must print the prompt and its fingerprint, and refuse
    rather than emit a partial one. Exit codes are the contract.

    These need a *covered* work item, so they use the committed consumer project
    (`git_project`) rather than the empty one `project` builds.
    """

    def test_compile_requires_a_budget(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        with pytest.raises(SystemExit):
            main(["compile", "MRB-M06"])

    def test_bad_identifier_is_two(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed identifier is a usage error, not an uncaught exception."""
        monkeypatch.chdir(git_project)
        assert main(["compile", "NOT-AN-ID", "--budget", "1000"]) == 2

    def test_zero_budget_is_two(self, git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06", "--budget", "0"]) == 2

    def test_uncovered_chain_is_four(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M99", "--budget", "1000"]) == 4

    def test_tiny_budget_is_five(self, git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Over budget has its own code, distinct from a usage error."""
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06", "--budget", "1"]) == 5

    def test_blocked_item_is_three(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06-S07", "--budget", "100000"]) == 3

    def test_compiles_and_prints_the_fingerprint_on_stderr(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06", "--budget", "100000"]) == 0
        captured = capsys.readouterr()
        assert "MRB-M06" in captured.out
        assert "fingerprint" in captured.err

    def test_json_carries_text_and_fingerprint(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06", "--budget", "100000", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["fingerprint"]
        assert payload["text"]
        assert payload["unit"] == "word"

    def test_manifest_omits_the_text(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["compile", "MRB-M06", "--budget", "100000", "--manifest"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert "text" not in payload
        assert payload["fingerprint"]


class TestIndex:
    def test_index_without_dsn_is_three(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        assert main(["index", "status"]) == 3

    def test_index_status_does_not_need_a_revision(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`status` reads the store; only build and verify read git.

        A missing `--rev` must not crash the command that inspects the index.
        """
        monkeypatch.chdir(project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        assert main(["index", "status"]) == 3  # fails on the DSN, not on a revision


class TestTopLevel:
    def test_no_command_is_usage_error(self) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_version_is_available(self) -> None:
        with pytest.raises(SystemExit):
            main(["--version"])
