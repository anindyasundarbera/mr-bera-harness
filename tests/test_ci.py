"""Tests for harness.ci.rehearse — the local pipeline rehearsal.

Its value depends on one property: it must mirror the real pipeline. A runner
whose stages silently drift from CI is worse than none, because a green local
run would then mean nothing.
"""

from __future__ import annotations

from harness.ci.rehearse import Pipeline, Stage, Step, default_pipeline


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
