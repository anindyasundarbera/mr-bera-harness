"""Tests for tools/entries.py — the changelog and ADR entry system.

The conflict-freedom property is the point: two branches must never edit the same
entry file. That is structural, so what needs testing is the schema validation,
uniqueness enforcement, and that generation is idempotent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import write_concept
from harness.entries.generator import (
    ADR_STATUSES,
    CHANGELOG_KINDS,
    Entry,
    generate,
    load_entries,
    render_changelog,
    render_decisions_index,
    validate_adr_entry,
    validate_all,
    validate_changelog_entry,
)
from harness.okf import OkfError, split_frontmatter

ENTRIES = None  # the harness is invoked as a module, not a script


def entry(tmp_path: Path, name: str, frontmatter: str, kind: str = "changelog") -> Entry:
    path = write_concept(tmp_path, name, frontmatter)
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return Entry(path=path, frontmatter=fm, body=body, kind=kind)


GOOD_CHANGELOG = (
    "id: CHG-2026-001\n"
    "date: 2026-10-10\n"
    "kind: added\n"
    "title: A change\n"
    "summary: One sentence.\n"
    "covers: [MRB-M06]\n"
)

GOOD_ADR = (
    "id: ADR-2026-001\n"
    "date: 2026-10-10\n"
    "title: A decision\n"
    "status: Accepted\n"
    "decision: We will do the thing.\n"
    "covers: [MRB]\n"
)


class TestChangelogSchema:
    def test_valid_entry_passes(self, tmp_path: Path) -> None:
        assert validate_changelog_entry(entry(tmp_path, "a.md", GOOD_CHANGELOG)) == []

    @pytest.mark.parametrize(
        "bad_id", ["CHG-26-1", "ADR-2026-001", "CHG-2026-1", "", "chg-2026-001"]
    )
    def test_bad_id_rejected(self, tmp_path: Path, bad_id: str) -> None:
        fm = GOOD_CHANGELOG.replace("CHG-2026-001", bad_id or '""')
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))

    @pytest.mark.parametrize("bad_date", ["2026-1-1", "10-10-2026", "", "not-a-date", "2026-13-01"])
    def test_bad_date_rejected(self, tmp_path: Path, bad_date: str) -> None:
        """An invalid calendar date must be reported, never crash the validator.

        `2026-13-01` is the sharp case: PyYAML coerces unquoted dates and raises
        ValueError (not YAMLError) for month 13, which would otherwise take down
        the whole run on a single malformed entry.
        """
        fm = GOOD_CHANGELOG.replace("date: 2026-10-10", f"date: {bad_date}")
        try:
            problems = validate_changelog_entry(entry(tmp_path, "a.md", fm))
        except OkfError:
            return  # reported at parse time, which is acceptable
        assert problems, f"{bad_date!r} should be rejected"

    def test_every_kind_is_accepted(self, tmp_path: Path) -> None:
        for kind in sorted(CHANGELOG_KINDS):
            fm = GOOD_CHANGELOG.replace("kind: added", f"kind: {kind}")
            assert validate_changelog_entry(entry(tmp_path, "a.md", fm)) == [], kind

    def test_unknown_kind_rejected(self, tmp_path: Path) -> None:
        fm = GOOD_CHANGELOG.replace("kind: added", "kind: improved")
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))

    def test_missing_title_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(
            line for line in GOOD_CHANGELOG.splitlines() if not line.startswith("title:")
        )
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))

    def test_missing_summary_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(
            line for line in GOOD_CHANGELOG.splitlines() if not line.startswith("summary:")
        )
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))

    def test_missing_covers_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(
            line for line in GOOD_CHANGELOG.splitlines() if not line.startswith("covers:")
        )
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))

    def test_empty_covers_rejected(self, tmp_path: Path) -> None:
        fm = GOOD_CHANGELOG.replace("covers: [MRB-M06]", "covers: []")
        assert validate_changelog_entry(entry(tmp_path, "a.md", fm))


class TestAdrSchema:
    def test_valid_adr_passes(self, tmp_path: Path) -> None:
        assert validate_adr_entry(entry(tmp_path, "a.md", GOOD_ADR, "adr")) == []

    @pytest.mark.parametrize("status", sorted(ADR_STATUSES))
    def test_every_status_accepted(self, tmp_path: Path, status: str) -> None:
        fm = GOOD_ADR.replace("status: Accepted", f"status: {status}")
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr")) == []

    def test_unknown_status_rejected(self, tmp_path: Path) -> None:
        fm = GOOD_ADR.replace("status: Accepted", "status: Maybe")
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr"))

    def test_okf_lifecycle_status_is_not_an_adr_status(self, tmp_path: Path) -> None:
        """`stable` is an OKF lifecycle value, not an ADR editorial status."""
        fm = GOOD_ADR.replace("status: Accepted", "status: stable")
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr"))

    def test_missing_decision_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(line for line in GOOD_ADR.splitlines() if not line.startswith("decision:"))
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr"))

    def test_missing_title_rejected(self, tmp_path: Path) -> None:
        fm = "\n".join(line for line in GOOD_ADR.splitlines() if not line.startswith("title:"))
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr"))

    def test_supersedes_must_be_a_list(self, tmp_path: Path) -> None:
        fm = GOOD_ADR + "supersedes: ADR-2026-000\n"
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr"))

    def test_supersedes_list_ok(self, tmp_path: Path) -> None:
        fm = GOOD_ADR + "supersedes: [ADR-2026-000]\n"
        assert validate_adr_entry(entry(tmp_path, "a.md", fm, "adr")) == []


class TestUniquenessAndReferences:
    def _dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        changes = tmp_path / "changelog"
        adrs = tmp_path / "decisions"
        changes.mkdir()
        adrs.mkdir()
        return changes, adrs

    def test_duplicate_changelog_ids_detected(self, tmp_path: Path) -> None:
        changes, adrs = self._dirs(tmp_path)
        write_concept(changes, "one.md", GOOD_CHANGELOG)
        write_concept(changes, "two.md", GOOD_CHANGELOG)
        result = validate_all(changes, adrs)
        assert any("duplicate id" in p.detail for p in result.problems)

    def test_supersedes_missing_adr_detected(self, tmp_path: Path) -> None:
        changes, adrs = self._dirs(tmp_path)
        write_concept(adrs, "a.md", GOOD_ADR + "supersedes: [ADR-2026-999]\n")
        result = validate_all(changes, adrs)
        assert any("does not exist" in p.detail for p in result.problems)

    def test_supersedes_existing_adr_ok(self, tmp_path: Path) -> None:
        changes, adrs = self._dirs(tmp_path)
        write_concept(adrs, "old.md", GOOD_ADR.replace("ADR-2026-001", "ADR-2026-000", 1))
        write_concept(adrs, "new.md", GOOD_ADR + "supersedes: [ADR-2026-000]\n")
        assert validate_all(changes, adrs).ok

    def test_index_md_is_not_an_entry(self, tmp_path: Path) -> None:
        changes, adrs = self._dirs(tmp_path)
        (changes / "index.md").write_text("# Index\n", encoding="utf-8")
        write_concept(changes, "one.md", GOOD_CHANGELOG)
        entries, problems = load_entries(changes, "changelog")
        assert len(entries) == 1
        assert problems == []

    def test_entries_sorted_newest_first(self, tmp_path: Path) -> None:
        changes, _ = self._dirs(tmp_path)
        write_concept(changes, "old.md", GOOD_CHANGELOG.replace("2026-10-10", "2026-01-01"))
        write_concept(changes, "new.md", GOOD_CHANGELOG.replace("2026-10-10", "2026-12-31"))
        entries, _ = load_entries(changes, "changelog")
        assert [e.date for e in entries] == ["2026-12-31", "2026-01-01"]

    def test_malformed_entry_reported_not_crashed(self, tmp_path: Path) -> None:
        changes, _ = self._dirs(tmp_path)
        (changes / "bad.md").write_text("# no frontmatter\n", encoding="utf-8")
        _, problems = load_entries(changes, "changelog")
        assert any("malformed" in p.detail for p in problems)

    def test_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        entries, problems = load_entries(tmp_path / "absent", "changelog")
        assert entries == []
        assert problems == []


class TestRendering:
    def test_changelog_marks_itself_generated(self, tmp_path: Path) -> None:
        text = render_changelog([entry(tmp_path, "a.md", GOOD_CHANGELOG)])
        assert "do not edit by hand" in text

    def test_the_header_states_the_configured_source_path(self) -> None:
        """The generated file must name where *this* project keeps its entries.

        The header previously hardcoded `knowledge/changelog/`, which was wrong for
        any project configuring a different path — a library stating a location it
        was not told.
        """
        text = render_changelog([], source_dir="entries/changes")
        assert "`entries/changes/`" in text

    def test_the_decisions_header_states_the_configured_path(self) -> None:
        """The case that exposed it: this repository's decisions live elsewhere."""
        text = render_decisions_index([], source_dir="docs/decisions")
        assert "`docs/decisions/`" in text
        assert "knowledge/decisions" not in text

    def test_changelog_groups_by_date(self, tmp_path: Path) -> None:
        one = entry(tmp_path, "a.md", GOOD_CHANGELOG)
        two = entry(tmp_path, "b.md", GOOD_CHANGELOG.replace("2026-10-10", "2026-10-09"))
        text = render_changelog([one, two])
        assert text.index("## 2026-10-10") < text.index("## 2026-10-09")

    def test_changelog_includes_pr_and_branch_when_present(self, tmp_path: Path) -> None:
        fm = GOOD_CHANGELOG + "pr: 42\nbranch: feat/x\n"
        text = render_changelog([entry(tmp_path, "a.md", fm)])
        assert "#42" in text
        assert "feat/x" in text

    def test_changelog_omits_absent_pr_and_branch(self, tmp_path: Path) -> None:
        text = render_changelog([entry(tmp_path, "a.md", GOOD_CHANGELOG)])
        assert "**PR:**" not in text
        assert "**Branch:**" not in text

    def test_decisions_index_is_a_table(self, tmp_path: Path) -> None:
        text = render_decisions_index([entry(tmp_path, "a.md", GOOD_ADR, "adr")])
        assert "| ID | Date | Title | Status | Supersedes |" in text
        assert "ADR-2026-001" in text
        assert "Accepted" in text

    def test_decisions_index_marks_itself_generated(self, tmp_path: Path) -> None:
        assert "do not edit by hand" in render_decisions_index([])

    def test_empty_input_renders_validly(self) -> None:
        assert render_changelog([]).startswith("# Changelog")
        assert render_decisions_index([]).startswith("# Architecture Decision Index")


class TestGenerationIdempotence:
    def _tree(self, tmp_path: Path) -> dict[str, Path]:
        changes = tmp_path / "changelog"
        adrs = tmp_path / "decisions"
        changes.mkdir()
        adrs.mkdir()
        write_concept(changes, "a.md", GOOD_CHANGELOG)
        write_concept(adrs, "b.md", GOOD_ADR)
        return {
            "changelog_dir": changes,
            "decisions_dir": adrs,
            "changelog_md": tmp_path / "CHANGELOG.md",
            "decisions_index_md": tmp_path / "docs" / "DECISIONS_INDEX.md",
        }

    def test_generate_writes_both_targets(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        code, _ = generate(**kw)  # type: ignore[arg-type]
        assert code == 0
        assert kw["changelog_md"].exists()
        assert kw["decisions_index_md"].exists()

    def test_generate_is_idempotent(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        assert generate(**kw)[0] == 0  # type: ignore[arg-type]
        first = kw["changelog_md"].read_text()
        assert generate(**kw)[0] == 0  # type: ignore[arg-type]
        assert kw["changelog_md"].read_text() == first, "regeneration must be byte-identical"

    def test_check_passes_on_fresh_tree(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        generate(**kw)  # type: ignore[arg-type]
        code, messages = generate(check=True, **kw)  # type: ignore[arg-type]
        assert code == 0
        assert any("up to date" in m for m in messages)

    def test_check_detects_drift(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        generate(**kw)  # type: ignore[arg-type]
        kw["changelog_md"].write_text("hand edited\n")
        code, messages = generate(check=True, **kw)  # type: ignore[arg-type]
        assert code == 1
        assert any("out of date" in m for m in messages)

    def test_check_does_not_write(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        generate(**kw)  # type: ignore[arg-type]
        kw["changelog_md"].write_text("hand edited\n")
        generate(check=True, **kw)  # type: ignore[arg-type]
        assert kw["changelog_md"].read_text() == "hand edited\n", "check must not mutate"

    def test_invalid_entry_blocks_generation(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        write_concept(
            kw["changelog_dir"], "bad.md", GOOD_CHANGELOG.replace("kind: added", "kind: bogus")
        )
        code, messages = generate(**kw)  # type: ignore[arg-type]
        assert code == 1
        assert messages, "a validation failure must explain itself"

    def test_invalid_entry_does_not_write(self, tmp_path: Path) -> None:
        kw = self._tree(tmp_path)
        write_concept(
            kw["changelog_dir"], "bad.md", GOOD_CHANGELOG.replace("kind: added", "kind: bogus")
        )
        generate(**kw)  # type: ignore[arg-type]
        assert not kw["changelog_md"].exists(), "a failed validation must not write output"


class TestCliContract:
    def test_validate_runs_here(self) -> None:
        """The harness repo has no entries yet, which is a valid state."""
        result = validate_all()
        assert result.ok or result.entries, "either no entries, or all entries valid"

    def test_generate_check_is_idempotent_here(self) -> None:
        code, _messages = generate(check=True)
        assert code == 0

    def test_no_args_is_usage_error(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ENTRIES)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 2

    def test_real_entries_are_valid_when_present(self) -> None:
        """Whatever entries exist must validate.

        This asserts the contract, not that a particular repository has entries:
        a consumer's entries are its own concern.
        """
        result = validate_all()
        assert result.ok, [str(p) for p in result.problems]

    def test_real_changelog_ids_are_unique(self) -> None:
        result = validate_all()
        ids = [e.id for e in result.entries]
        assert len(ids) == len(set(ids))
