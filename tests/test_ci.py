"""Tests for harness.ci.rehearse — the local pipeline rehearsal.

Its value depends on one property: it must mirror the real pipeline. A runner
whose stages silently drift from CI is worse than none, because a green local
run would then mean nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

from harness.ci import rehearse
from harness.ci.rehearse import (
    Pipeline,
    Stage,
    Step,
    check_parity,
    default_pipeline,
    repo_root,
    run_stage,
    stages,
)


class TestPipelineDefinition:
    def test_default_pipeline_has_stages(self) -> None:
        pipeline = default_pipeline()
        assert pipeline.stages, "a pipeline with no stages proves nothing"

    def test_every_stage_has_steps(self) -> None:
        for stage in default_pipeline().stages:
            assert stage.steps, f"{stage.name} has no steps"

    def test_every_step_has_label_and_argv(self) -> None:
        for stage in default_pipeline().stages:
            for step in stage.steps:
                assert step.label
                assert step.argv
                assert all(isinstance(a, str) for a in step.argv)

    def test_names_are_unique(self) -> None:
        names = [s.name for s in default_pipeline().stages]
        assert len(names) == len(set(names))

    def test_pipeline_is_configurable(self) -> None:
        """A consumer defines its own stages; the harness supplies no defaults."""
        pipeline = Pipeline(
            stages=[
                Stage(name="lint", description="lint", steps=[Step("ruff", ["ruff", "check", "."])])
            ]
        )
        assert [s.name for s in pipeline.stages] == ["lint"]


class TestParityConcept:
    def test_parity_reports_missing_stages(self) -> None:
        """A CI job with no local stage must be reported, not ignored."""
        pipeline = Pipeline(stages=[Stage("lint", "lint", [Step("x", ["true"])])])
        result = pipeline.parity(["lint", "test", "governance"])
        assert "test" in result.missing
        assert "governance" in result.missing
        assert not result.ok

    def test_parity_passes_when_aligned(self) -> None:
        pipeline = Pipeline(stages=[Stage(n, n, [Step(n, ["true"])]) for n in ("lint", "test")])
        result = pipeline.parity(["lint", "test"])
        assert result.ok
        assert result.missing == []

    def test_parity_reports_extra_stages(self) -> None:
        pipeline = Pipeline(stages=[Stage(n, n, [Step(n, ["true"])]) for n in ("lint", "extra")])
        assert "extra" in pipeline.parity(["lint"]).extra


class TestRepoRootRegression:
    """The rehearsal must run in the invoking repository.

    `REPO_ROOT` was `Path(__file__).resolve().parent.parent`, which resolved to
    the installed package (`.../src/harness`). Every stage then ran there: the
    wheel build found no `pyproject.toml`, pytest found no `tests/`, the
    self-check found no `harness.toml`, and the parity check reported success
    while having read nothing. These tests fail if that returns.
    """

    def test_repo_root_is_the_invoking_directory(self, project: Path) -> None:
        assert repo_root(project) == project.resolve()

    def test_repo_root_is_not_the_package_directory(self) -> None:
        package_dir = Path(rehearse.__file__).resolve().parent
        assert repo_root() != package_dir
        assert repo_root() != package_dir.parent

    def test_run_stage_executes_in_the_invoking_repository(
        self, project: Path, tmp_path: Path
    ) -> None:
        """A stage that writes a file must write it into the project, not the package."""
        marker = "stage-ran-here.txt"
        stage = Stage(
            "probe",
            "probe",
            [
                Step(
                    "touch",
                    [sys.executable, "-c", f"open({marker!r}, 'w').close()"],
                )
            ],
        )
        passed, _ = run_stage(stage, project)
        assert passed
        assert (project / marker).exists()
        assert not (Path(rehearse.__file__).resolve().parent / marker).exists()

    def test_parity_reads_the_workflow_file(self, tmp_path: Path) -> None:
        """Parity must actually parse the workflow, not compare against nothing.

        The workflow declares a job (`governance`) that the default pipeline has
        no stage for. If parity did not read the file it could not report it.
        """
        workflow = tmp_path / "ci.yml"
        workflow.write_text(
            "name: CI\non:\n  push: {}\njobs:\n"
            "  lint:\n    steps: []\n  test:\n    steps: []\n  governance:\n    steps: []\n",
            encoding="utf-8",
        )
        ok, messages = check_parity(workflow, tmp_path)
        joined = " ".join(messages)
        assert "lint" in joined and "test" in joined
        assert "governance" in joined
        assert not ok

    def test_parity_reports_a_missing_workflow(self, tmp_path: Path) -> None:
        ok, messages = check_parity(tmp_path / "absent.yml", tmp_path)
        assert not ok
        assert "workflow not found" in " ".join(messages)

    def test_selfcheck_stages_do_not_reference_removed_tools(self) -> None:
        """The stages once invoked `tools/*.py`, which no longer exists."""
        selfcheck = next(s for s in stages() if s.name == "selfcheck")
        for step in selfcheck.steps:
            assert not any("tools/" in arg for arg in step.argv), step.label

    def test_selfcheck_does_not_gate_the_build_on_session_guards(self) -> None:
        """A build check must be able to pass on the default branch.

        The session guards refuse a protected branch (ADR-2026-004), so wiring
        them into a stage made `harness ci` — and CI on every push to `main` —
        fail by definition. Session preconditions and tree invariants are
        different questions and are enforced in different places.
        """
        selfcheck = next(s for s in stages() if s.name == "selfcheck")
        for step in selfcheck.steps:
            assert "guards" not in step.argv, step.label

    def test_no_stage_invokes_the_session_guards(self) -> None:
        for stage in stages():
            for step in stage.steps:
                assert "guards" not in step.argv, f"{stage.name}/{step.label}"

    def test_mypy_stage_targets_the_package_like_ci(self) -> None:
        typecheck = next(s for s in stages() if s.name == "typecheck")
        assert "src" in typecheck.steps[0].argv

    def test_the_context_step_accepts_the_documented_exit_codes(self) -> None:
        """`harness context` exits 3 or 4 by design, so the step must allow them."""
        selfcheck = next(s for s in stages() if s.name == "selfcheck")
        step = next(s for s in selfcheck.steps if "context" in s.argv)
        assert set(step.ok_exit_codes) >= {0, 3, 4}

    def test_a_step_fails_on_an_unexpected_exit_code(self, project: Path) -> None:
        stage = Stage(
            "probe",
            "probe",
            [Step("wrong code", [sys.executable, "-c", "raise SystemExit(7)"], ok_exit_codes=(0,))],
        )
        passed, messages = run_stage(stage, project)
        assert not passed
        assert "exit 7" in " ".join(messages)
