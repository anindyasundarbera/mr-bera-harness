"""Tests for harness.routing.invariants — the structural checks.

These make "one canonical copy per artifact" a test rather than a hope, so a
regression in the validator itself must be caught, not just one in a bundle.
"""

from __future__ import annotations

from pathlib import Path

from conftest import write_concept
from harness.config import load_config
from harness.routing.invariants import (
    Report,
    gap_states,
    known_decomposition_ids,
    known_modules,
    validate_routing,
)

DECOMP = {"MRB-M06", "MRB-M06-S07", "MRB-M06-S14", "MRB-M06-S14-C02"}
MODULES = {"MRB-M03", "MRB-M06"}


def run(project: Path) -> Report:
    return validate_routing(load_config(project))


def checks(report: Report) -> set[int]:
    return {v.check for v in report.violations}


class TestCleanProject:
    def test_empty_bundle_is_clean(self, project: Path) -> None:
        assert run(project).violations == []

    def test_valid_concept_is_clean(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: T\nmodule: MRB-M06\ncovers: [MRB-M06]")
        assert run(project).violations == []


class TestProhibitedKeys:
    def test_lifecycle_status_allowed(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: T\nmodule: MRB-M06\nstatus: draft")
        assert run(project).violations == []

    def test_unknown_status_rejected(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: T\nmodule: MRB-M06\nstatus: finished")
        assert run(project).violations

    def test_decision_status_rejected(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: T\ndecision_status: OwnerSelected")
        assert run(project).violations

    def test_value_key_rejected(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: T\nvalue: 42")
        assert run(project).violations

    def test_state_only_on_unknown(self, project: Path) -> None:
        write_concept(project / "knowledge", "a.md", "type: Concept\nmodule: MRB-M06\nstate: Open")
        assert run(project).violations


class TestStructuralChecks:
    def test_duplicate_canonical_detected(self, project: Path) -> None:
        for name in ("a", "b"):
            write_concept(
                project / "knowledge",
                f"{name}.md",
                "type: T\nmodule: MRB-M06\nclass: spec\ncanonical: true",
            )
        assert run(project).violations

    def test_different_classes_may_each_be_canonical(self, project: Path) -> None:
        write_concept(
            project / "knowledge", "a.md", "type: T\nmodule: MRB-M06\nclass: spec\ncanonical: true"
        )
        write_concept(
            project / "knowledge",
            "b.md",
            "type: T\nmodule: MRB-M06\nclass: unknowns\ncanonical: true",
        )
        assert run(project).violations == []

    def test_two_modules_claiming_one_key_detected(self, project: Path) -> None:
        write_concept(
            project / "knowledge",
            "a.md",
            "type: T\nmodule: MRB-M06\ndo_not_use_for: [commerce-truth]",
        )
        write_concept(
            project / "knowledge",
            "b.md",
            "type: T\nmodule: MRB-M03\ndo_not_use_for: [commerce-truth]",
        )
        assert run(project).violations


class TestHelpers:
    def test_missing_register_yields_empty(self, tmp_path: Path) -> None:
        assert gap_states(load_config(tmp_path)) == {}

    def test_known_ids_from_decomposition(self, project: Path) -> None:
        (project / "docs" / "PROJECT_DECOMPOSITION.md").write_text(
            "# Decomp\n\nMRB-M06 MRB-M06-S07\n", encoding="utf-8"
        )
        ids = known_decomposition_ids(project / "docs" / "PROJECT_DECOMPOSITION.md")
        assert "MRB-M06" in ids

    def test_known_modules_from_registry(self, project: Path) -> None:
        (project / "docs" / "MODULE_REGISTRY.md").write_text("MRB-M06\nMRB-M03\n", encoding="utf-8")
        mods = known_modules(project / "docs" / "MODULE_REGISTRY.md")
        assert {"MRB-M03", "MRB-M06"} <= mods


class TestReport:
    def test_report_ok_is_true_when_empty(self) -> None:
        assert Report().ok

    def test_report_not_ok_with_violations(self) -> None:
        report = Report()
        report.add(1, "x", "bad")
        assert not report.ok


class TestDocFrontmatterChecks:
    """The checks that make documentation frontmatter machine-verifiable."""

    def _docs(self, project: Path) -> Path:
        return project / "docs"

    def test_id_mismatch_detected(self, project: Path) -> None:
        (self._docs(project) / "X.md").write_text(
            "---\nid: WRONG\nclass: spec\ncanonical: true\n---\n\n> ID: RIGHT-001\n",
            encoding="utf-8",
        )
        assert run(project).violations

    def test_matching_id_passes(self, project: Path) -> None:
        (self._docs(project) / "X.md").write_text(
            "---\nid: RIGHT-001\nclass: spec\ncanonical: true\n---\n\n> ID: RIGHT-001\n",
            encoding="utf-8",
        )
        assert run(project).violations == []

    def test_unresolvable_depends_on_detected(self, project: Path) -> None:
        (self._docs(project) / "X.md").write_text(
            "---\nid: X\nclass: spec\ncanonical: true\ndepends-on: [GHOST.md]\n---\n\n> ID: X\n",
            encoding="utf-8",
        )
        assert run(project).violations

    def test_resolvable_depends_on_passes(self, project: Path) -> None:
        (self._docs(project) / "A.md").write_text("# A\n", encoding="utf-8")
        (self._docs(project) / "X.md").write_text(
            "---\nid: X\nclass: spec\ncanonical: true\ndepends-on: [A.md]\n---\n\n> ID: X\n",
            encoding="utf-8",
        )
        assert run(project).violations == []

    def test_document_without_frontmatter_is_not_an_error(self, project: Path) -> None:
        """A doc with no frontmatter is do-not-load, not a defect."""
        (self._docs(project) / "plain.md").write_text("# No frontmatter\n", encoding="utf-8")
        assert run(project).violations == []

    def test_malformed_frontmatter_is_reported(self, project: Path) -> None:
        (self._docs(project) / "bad.md").write_text("---\nunclosed: [\n", encoding="utf-8")
        assert run(project).violations


class TestGapMirror:
    """Check 9 keeps an Unknown's state honest against the register."""

    def _register(self, project: Path) -> None:
        (project / "docs" / "GAP_REGISTER.md").write_text(
            "| Gap ID | Parent | Gap | State | Next |\n"
            "|---|---|---|---|---|\n"
            "| GAP-CTL-002 | M06 | Store | BlockedOwner | decide |\n",
            encoding="utf-8",
        )
        # The fixture config already declares [registries.gaps]; TOML forbids
        # declaring a table twice, so the path is set on the existing table.
        text = (project / "harness.toml").read_text()
        (project / "harness.toml").write_text(text, encoding="utf-8")

    def test_matching_state_passes(self, project: Path) -> None:
        self._register(project)
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\nmodule: MRB-M06\nstate: BlockedOwner\ngap: GAP-CTL-002",
        )
        assert run(project).violations == []

    def test_mismatched_state_detected(self, project: Path) -> None:
        self._register(project)
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\nmodule: MRB-M06\nstate: Open\ngap: GAP-CTL-002",
        )
        assert run(project).violations

    def test_unknown_gap_id_detected(self, project: Path) -> None:
        self._register(project)
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\nmodule: MRB-M06\nstate: BlockedOwner\ngap: GAP-NOPE-999",
        )
        assert run(project).violations
