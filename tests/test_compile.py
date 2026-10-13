"""Tests for the prompt compiler.

The compiler's whole value is that it is a *pure function* of a revision. So the
tests concentrate on the three ways that can be lost:

* nondeterminism — the same revision must compile the same bytes and fingerprint;
* a fingerprint that does not bind its content — a swapped entry must change it;
* silent partiality — a selection that does not fit must be refused, never
  truncated, and a blocked work item must refuse rather than compile.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import git_commit
from harness.compile.prompt import (
    EXIT_BLOCKED,
    EXIT_NO_SELECTION,
    EXIT_OVER_BUDGET,
    EXIT_USAGE,
    CompileError,
    Entry,
    _fingerprint,
    compile_prompt,
)
from harness.compile.tokens import UNIT, count_units
from harness.config import load_config
from harness.extract.source import commit_sha


@pytest.fixture
def config(git_project: Path):
    return load_config(git_project)


class TestTokenCounting:
    def test_counts_words(self) -> None:
        assert count_units("one two three") == 3

    def test_is_deterministic(self) -> None:
        assert count_units("a b\nc") == count_units("a b\nc")

    def test_whitespace_does_not_change_the_count(self) -> None:
        assert count_units("a  b\n\nc") == 3

    def test_empty_text_is_zero(self) -> None:
        assert count_units("") == 0

    def test_the_unit_is_named(self) -> None:
        """A count whose unit is unstated is not a measurement."""
        assert UNIT == "word"


class TestCompiles:
    def test_compiles_a_covered_work_item(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert compiled.work_id == "MRB-M06"
        assert compiled.entries
        assert compiled.fits

    def test_records_the_commit_it_compiled_from(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert compiled.commit_sha == git_commit_sha(git_project)

    def test_prompt_names_the_work_item_and_revision(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert "MRB-M06" in compiled.text
        assert "Revision: HEAD" in compiled.text

    def test_prompt_carries_provenance_for_each_entry(self, config, git_project: Path) -> None:
        """Every entry states where it came from, so a claim can be traced."""
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        for entry in compiled.entries:
            assert f"## {entry.concept_id}" in compiled.text
            assert f"- source: {entry.path}" in compiled.text

    def test_used_matches_the_rendered_text(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert compiled.used == count_units(compiled.text)

    def test_unit_is_recorded(self, config, git_project: Path) -> None:
        assert compile_prompt(config, "MRB-M06", budget=100_000).unit == UNIT


def git_commit_sha(root: Path) -> str:
    return commit_sha(root)


class TestDeterminism:
    def test_same_revision_compiles_the_same_bytes(self, config, git_project: Path) -> None:
        first = compile_prompt(config, "MRB-M06", budget=100_000)
        second = compile_prompt(config, "MRB-M06", budget=100_000)
        assert first.text == second.text
        assert first.fingerprint == second.fingerprint

    def test_a_pinned_revision_is_reproducible(self, config, git_project: Path) -> None:
        rev = commit_sha(git_project)
        first = compile_prompt(config, "MRB-M06", budget=100_000, rev=rev)
        second = compile_prompt(config, "MRB-M06", budget=100_000, rev=rev)
        assert first.fingerprint == second.fingerprint

    def test_an_uncommitted_edit_is_invisible(self, config, git_project: Path) -> None:
        """The compiler reads a revision, not the working tree."""
        before = compile_prompt(config, "MRB-M06", budget=100_000).fingerprint

        target = git_project / "knowledge" / "modules" / "M06-engine.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\n## Uncommitted\n", encoding="utf-8"
        )

        assert compile_prompt(config, "MRB-M06", budget=100_000).fingerprint == before

    def test_a_committed_edit_changes_the_fingerprint(self, config, git_project: Path) -> None:
        before = compile_prompt(config, "MRB-M06", budget=100_000).fingerprint

        target = git_project / "knowledge" / "modules" / "M06-engine.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\n## Committed\n", encoding="utf-8"
        )
        git_commit(git_project, "docs: change")

        assert compile_prompt(config, "MRB-M06", budget=100_000).fingerprint != before

    def test_the_budget_does_not_change_the_fingerprint(self, config, git_project: Path) -> None:
        """A generous budget and a tight one compile the same prompt.

        The budget bounds whether a prompt is admissible, not its content, so the
        fingerprint must not depend on it.
        """
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        roomy = compile_prompt(config, "MRB-M06", budget=compiled.used * 10)
        assert roomy.fingerprint == compiled.fingerprint


class TestFingerprintBindsContent:
    """A fingerprint that does not bind its content is decoration."""

    def test_text_change_changes_the_digest(self) -> None:
        a = _fingerprint("same", (), "MRB-M06", "HEAD")
        b = _fingerprint("different", (), "MRB-M06", "HEAD")
        assert a != b

    def test_work_id_change_changes_the_digest(self) -> None:
        assert _fingerprint("t", (), "MRB-M06", "HEAD") != _fingerprint("t", (), "MRB-M07", "HEAD")

    def test_revision_change_changes_the_digest(self) -> None:
        assert _fingerprint("t", (), "MRB-M06", "HEAD") != _fingerprint("t", (), "MRB-M06", "main")

    def test_structure_change_changes_the_digest_even_with_identical_text(self) -> None:
        """The digest covers the manifest, so a swapped entry cannot pass.

        Hashing the text alone would let a same-length document be substituted
        without the fingerprint noticing.
        """

        def entry(concept_id: str) -> Entry:
            return Entry(
                concept_id=concept_id,
                path=f"{concept_id}.md",
                title="T",
                read_budget="must-read",
                trust="unverified",
                status="stable",
                stale=None,
                covers=("MRB-M06",),
                units=1,
                text="x",
            )

        assert _fingerprint("x", (entry("a"),), "MRB-M06", "HEAD") != _fingerprint(
            "x", (entry("b"),), "MRB-M06", "HEAD"
        )


class TestRefusesRatherThanTruncates:
    def test_over_budget_is_refused(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        with pytest.raises(CompileError) as caught:
            compile_prompt(config, "MRB-M06", budget=compiled.used - 1)
        assert caught.value.exit_code == EXIT_OVER_BUDGET

    def test_the_refusal_names_the_shortfall(self, config, git_project: Path) -> None:
        with pytest.raises(CompileError, match="will not silently drop context"):
            compile_prompt(config, "MRB-M06", budget=1)

    def test_exactly_the_budget_is_accepted(self, config, git_project: Path) -> None:
        """The boundary is inclusive: a prompt that fits exactly must compile."""
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        exact = compile_prompt(config, "MRB-M06", budget=compiled.used)
        assert exact.used == exact.budget

    def test_a_blocked_work_item_is_refused(self, config, git_project: Path) -> None:
        with pytest.raises(CompileError) as caught:
            compile_prompt(config, "MRB-M06-S07", budget=100_000)
        assert caught.value.exit_code == EXIT_BLOCKED

    def test_the_refusal_names_the_blocker(self, config, git_project: Path) -> None:
        with pytest.raises(CompileError, match="DESIGN-RUBRIC-01"):
            compile_prompt(config, "MRB-M06-S07", budget=100_000)

    def test_an_uncovered_chain_is_refused(self, config, git_project: Path) -> None:
        with pytest.raises(CompileError) as caught:
            compile_prompt(config, "MRB-M99", budget=100_000)
        assert caught.value.exit_code == EXIT_NO_SELECTION

    def test_a_non_positive_budget_is_a_usage_error(self, config, git_project: Path) -> None:
        with pytest.raises(CompileError) as caught:
            compile_prompt(config, "MRB-M06", budget=0)
        assert caught.value.exit_code == EXIT_USAGE

    @pytest.mark.parametrize("budget", [-1, 0])
    def test_invalid_budgets_are_rejected(self, config, git_project: Path, budget: int) -> None:
        with pytest.raises(CompileError, match="positive number"):
            compile_prompt(config, "MRB-M06", budget=budget)


class TestExclusion:
    def test_do_not_use_for_excludes_a_concept(self, config, git_project: Path) -> None:
        """A concept that forbids a state must be named as excluded, not dropped."""
        path = git_project / "knowledge" / "modules" / "excluded.md"
        path.write_text(
            "---\ntype: Concept\nmodule: MRB-M06\ncovers: [MRB-M06]\n"
            "read_budget: must-read\ndo_not_use_for: [auth-model]\n---\n\nBody.\n",
            encoding="utf-8",
        )
        git_commit(git_project, "docs: add excluded concept")

        compiled = compile_prompt(config, "MRB-M06", budget=100_000, defining=["auth-model"])
        excluded = {item["concept_id"] for item in compiled.excluded}
        assert "modules/excluded" in excluded
        assert "modules/excluded" not in {e.concept_id for e in compiled.entries}

    def test_without_defining_it_is_loaded(self, config, git_project: Path) -> None:
        path = git_project / "knowledge" / "modules" / "excluded2.md"
        path.write_text(
            "---\ntype: Concept\nmodule: MRB-M06\ncovers: [MRB-M06]\n"
            "read_budget: must-read\ndo_not_use_for: [auth-model]\n---\n\nBody.\n",
            encoding="utf-8",
        )
        git_commit(git_project, "docs: add concept")
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert "modules/excluded2" in {e.concept_id for e in compiled.entries}


class TestManifest:
    def test_manifest_excludes_the_prompt_text(self, config, git_project: Path) -> None:
        """The manifest is an audit record; duplicating the text would be a second
        thing to keep in step with it."""
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert "text" not in compiled.manifest()

    def test_manifest_carries_the_fingerprint_and_provenance(
        self, config, git_project: Path
    ) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        manifest = compiled.manifest()
        assert manifest["fingerprint"] == compiled.fingerprint
        assert manifest["commit_sha"] == compiled.commit_sha
        assert manifest["unit"] == UNIT
        assert manifest["budget"] == 100_000

    def test_manifest_is_json_serializable(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        json.dumps(compiled.manifest())
        json.dumps(compiled.as_dict())

    def test_manifest_lists_every_entry(self, config, git_project: Path) -> None:
        compiled = compile_prompt(config, "MRB-M06", budget=100_000)
        assert len(compiled.manifest()["entries"]) == len(compiled.entries)
