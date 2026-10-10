"""Tests for harness.routing — the identifier grammar and context resolution.

These replace MrBera's original tests, because the routing layer changed
structurally: the grammar is now derived from configuration rather than hardcoded,
so the tests must assert the *contract* rather than one project's identifiers.
"""

from __future__ import annotations

import pytest

from conftest import write_concept
from harness.config import Identity, load_config
from harness.okf import OkfError
from harness.routing import parent_chain, parse_work_id, resolve_context
from harness.routing.resolve import render


class TestParseWorkId:
    def test_splits_into_levels(self) -> None:
        parsed = parse_work_id("MRB-M06-S07-C03")
        assert parsed.prefix == "MRB"
        assert parsed.segments == ("M06", "S07", "C03")
        assert parsed.depth == 3

    def test_rejects_malformed(self) -> None:
        for bad in ("", "MRB", "MRB-X", "MRB-M6", "MRB-M06-S7", "NOPE-M06"):
            with pytest.raises(OkfError, match="not a valid"):
                parse_work_id(bad)

    def test_honours_a_custom_grammar(self) -> None:
        """The whole point of the config layer: another project names work its way."""
        identity = Identity(name="Other", id_prefix="TASK", levels=("P", "T"), widths=(3, 4))
        parsed = parse_work_id("TASK-P001-T0002", identity)
        assert parsed.segments == ("P001", "T0002")


class TestParentChain:
    @pytest.mark.parametrize(
        ("work_id", "expected"),
        [
            ("MRB-M06", ["MRB-M06"]),
            ("MRB-M06-S07", ["MRB-M06-S07", "MRB-M06"]),
            ("MRB-M06-S07-C03", ["MRB-M06-S07-C03", "MRB-M06-S07", "MRB-M06"]),
            (
                "MRB-M06-S07-C03-W01-A02",
                [
                    "MRB-M06-S07-C03-W01-A02",
                    "MRB-M06-S07-C03-W01",
                    "MRB-M06-S07-C03",
                    "MRB-M06-S07",
                    "MRB-M06",
                ],
            ),
        ],
    )
    def test_chain_is_most_specific_first(self, work_id: str, expected: list[str]) -> None:
        assert parent_chain(work_id) == expected

    def test_chain_always_reaches_the_module(self) -> None:
        """A truncated chain under-selects context, which is a silent failure."""
        assert parent_chain("MRB-M06-S07-C03-W01-A02")[-1] == "MRB-M06"

    def test_whitespace_tolerated(self) -> None:
        assert parent_chain("  MRB-M06-S07  ")[0] == "MRB-M06-S07"


class TestResolveContext:
    def _bundle(self, project) -> None:
        write_concept(
            project / "knowledge",
            "mod/arch.md",
            "type: Module\ncovers: [MRB-M06]\nread_budget: must-read\nmodule: MRB-M06",
        )
        write_concept(
            project / "knowledge",
            "mod/s07.md",
            "type: Concept\ncovers: [MRB-M06-S07]\nread_budget: must-read\nmodule: MRB-M06",
        )
        write_concept(
            project / "knowledge",
            "other/thing.md",
            "type: Concept\ncovers: [MRB-M03]\nread_budget: must-read\nmodule: MRB-M03",
        )

    def test_selects_only_intersecting_covers(self, project) -> None:
        self._bundle(project)
        result = resolve_context(load_config(project), "MRB-M06-S07-C03")
        assert {i["concept_id"] for i in result.load} == {"mod/arch", "mod/s07"}

    def test_unrelated_module_is_not_loaded(self, project) -> None:
        self._bundle(project)
        result = resolve_context(load_config(project), "MRB-M06-S07")
        assert "other/thing" not in {i["concept_id"] for i in result.load}

    def test_do_not_use_for_excludes_when_defining(self, project) -> None:
        write_concept(
            project / "knowledge",
            "commerce.md",
            "type: Concept\ncovers: [MRB-M06]\nmodule: MRB-M06\ndo_not_use_for: [commerce-truth]",
        )
        result = resolve_context(load_config(project), "MRB-M06", defining=["commerce-truth"])
        assert "commerce" not in {i["concept_id"] for i in result.load}
        assert result.excluded

    def test_do_not_use_for_does_not_exclude_otherwise(self, project) -> None:
        write_concept(
            project / "knowledge",
            "commerce.md",
            "type: Concept\ncovers: [MRB-M06]\nmodule: MRB-M06\ndo_not_use_for: [commerce-truth]",
        )
        result = resolve_context(load_config(project), "MRB-M06", defining=["editorial-policy"])
        assert "commerce" in {i["concept_id"] for i in result.load}

    def test_unknowns_are_stops_never_loadable(self, project) -> None:
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\ncovers: [MRB-M06]\nmodule: MRB-M06\n"
            "blocks: [MRB-M06-S07]\nstate: BlockedOwner\nblocker: X-01",
        )
        result = resolve_context(load_config(project), "MRB-M06-S07")
        assert "u" not in {i["concept_id"] for i in result.load}
        assert any(s["concept_id"] == "u" for s in result.stop_conditions)

    def test_unknown_blocking_elsewhere_is_not_a_stop(self, project) -> None:
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\ncovers: [MRB-M06]\nmodule: MRB-M06\n"
            "blocks: [MRB-M06-S12]\nstate: BlockedOwner\nblocker: X-01",
        )
        assert resolve_context(load_config(project), "MRB-M06-S07").stop_conditions == []

    def test_read_order_puts_must_read_first(self, project) -> None:
        write_concept(
            project / "knowledge",
            "a.md",
            "type: Concept\ncovers: [MRB-M06]\nread_budget: reference-only\nmodule: MRB-M06",
        )
        write_concept(
            project / "knowledge",
            "b.md",
            "type: Concept\ncovers: [MRB-M06]\nread_budget: must-read\nmodule: MRB-M06",
        )
        result = resolve_context(load_config(project), "MRB-M06")
        assert [i["read_budget"] for i in result.load] == ["must-read", "reference-only"]

    def test_do_not_load_is_excluded(self, project) -> None:
        write_concept(
            project / "knowledge",
            "quiet.md",
            "type: Concept\ncovers: [MRB-M06]\nread_budget: do-not-load\nmodule: MRB-M06",
        )
        result = resolve_context(load_config(project), "MRB-M06")
        assert "quiet" not in {i["concept_id"] for i in result.load}


class TestExitCodeContract:
    """The load-bearing behaviour: an agent cannot silently proceed."""

    def test_stop_condition_is_three(self, project) -> None:
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\ncovers: [MRB-M06]\nblocks: [MRB-M06]\n"
            "state: BlockedOwner\nblocker: X-01",
        )
        assert resolve_context(load_config(project), "MRB-M06").exit_code() == 3

    def test_uncovered_chain_is_four(self, project) -> None:
        assert resolve_context(load_config(project), "MRB-M06-S07").exit_code() == 4

    def test_resolved_is_zero(self, project) -> None:
        write_concept(
            project / "knowledge", "a.md", "type: Concept\ncovers: [MRB-M06]\nmodule: MRB-M06"
        )
        assert resolve_context(load_config(project), "MRB-M06").exit_code() == 0

    def test_stop_takes_precedence_over_uncovered(self, project) -> None:
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\ncovers: [MRB-M06]\nblocks: [MRB-M06]\n"
            "state: BlockedOwner\nblocker: X-01",
        )
        assert resolve_context(load_config(project), "MRB-M06").exit_code() == 3

    def test_must_stop_flag_is_true_in_both_cases(self, project) -> None:
        assert resolve_context(load_config(project), "MRB-M06-S07").must_stop is True


class TestRendering:
    def test_empty_load_explains_the_required_action(self, project) -> None:
        assert "BlockedDependency" in render(resolve_context(load_config(project), "MRB-M06"))

    def test_stop_renders_blocker_and_consequence(self, project) -> None:
        write_concept(
            project / "knowledge",
            "u.md",
            "type: Unknown\ncovers: [MRB-M06]\nblocks: [MRB-M06]\n"
            "title: A Blocker\nstate: BlockedOwner\nblocker: TEST-01\n"
            "if_you_guess: Bad things\nmust_not_do: [Guessing]",
        )
        text = render(resolve_context(load_config(project), "MRB-M06"))
        assert "TEST-01" in text and "Bad things" in text and "Guessing" in text
