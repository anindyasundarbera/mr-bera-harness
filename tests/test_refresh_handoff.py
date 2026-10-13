"""Tests for tools/refresh_handoff.py — the handoff's mechanical facts.

The handoff is the document a new session is told to trust first. Its narrative is
written by hand, deliberately: a script that generated the story of what was built
would be inventing a handoff. But the handful of facts inside it — how many concepts,
entries and declarations the repository holds — are exactly what a machine knows, and
leaving them to be refreshed by hand is how `CHG-2026-016` and `CHG-2026-020` happened.

These tests pin the parts that must not drift:

- the splice touches **only** the marked region;
- a missing marker is a refusal, not a silent no-op that reports success;
- `--check` exits 1 on a stale region and 2 on a handoff it cannot parse;
- **the region holds no fact about the checkout or the machine**, because such a fact
  would be stale the moment it was committed (a file cannot know its own commit) or
  would flap between environments. That is asserted directly, not assumed.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from refresh_handoff import (  # noqa: E402 - after the path insert above
    HANDOFF,
    MARKER_END,
    MARKER_START,
    Facts,
    collect_facts,
    current_region,
    main,
    render_facts,
    splice,
)

SAMPLE = Facts(
    generated_by="mr-bera-harness 0.1.0",
    concepts=21,
    entries=41,
    entry_problems=0,
    test_modules=23,
    declarations=2,
    commit_types=11,
)


def document_with(body: str = "old\n") -> str:
    return f"# Handoff\n\nprose above\n\n{MARKER_START}\n{body}{MARKER_END}\n\nprose below\n"


class TestRender:
    def test_every_derived_fact_appears(self) -> None:
        """A fact that is collected but not rendered is a fact nobody sees."""
        table = render_facts(SAMPLE)
        for value in ("21", "41", "23", "2", "11"):
            assert value in table, f"{value!r} was collected but not rendered"

    def test_a_zero_problem_count_is_stated(self) -> None:
        assert "0 problem(s)" in render_facts(SAMPLE)

    def test_no_environment_or_checkout_fact_is_rendered(self) -> None:
        """The rule that keeps `--check` able to settle.

        A revision, a dirty flag or a test count describes the checkout or the machine,
        not the repository. Rendered, the region would be stale the moment it was
        committed, or would differ between a laptop and CI. `Facts` must not carry them
        at all — asserted on the dataclass fields, so re-adding one fails here.
        """
        fields = {f.name for f in dataclasses.fields(Facts)}
        assert not (fields & {"revision", "branch", "dirty", "test_count", "test_skipped"}), (
            "a fact about the checkout or the environment was reintroduced; the region "
            "can then never be current after a commit"
        )
        rendered = render_facts(SAMPLE)
        for word in ("Revision", "Working tree", "passed", "skipped"):
            assert word not in rendered, f"{word!r} describes the checkout, not the repo"


class TestSplice:
    def test_only_the_region_changes(self) -> None:
        """The script owns the markers and nothing else; prose must survive byte-exact."""
        original = document_with()
        updated = splice(original, render_facts(SAMPLE))
        assert updated.startswith("# Handoff\n\nprose above\n\n")
        assert updated.endswith("\n\nprose below\n")
        assert render_facts(SAMPLE) in updated
        assert "old\n" not in updated

    def test_a_missing_start_marker_is_refused(self) -> None:
        """A silent no-op would report success while refreshing nothing."""
        with pytest.raises(ValueError, match="harness:handoff-facts"):
            splice(f"# Handoff\n{MARKER_END}\n", "new\n")

    def test_a_missing_end_marker_is_refused(self) -> None:
        with pytest.raises(ValueError, match="harness:handoff-facts"):
            splice(f"# Handoff\n{MARKER_START}\n", "new\n")

    def test_splicing_twice_is_idempotent(self) -> None:
        """The scheduled job may run against an already-current handoff."""
        once = splice(document_with(), render_facts(SAMPLE))
        twice = splice(once, render_facts(SAMPLE))
        assert once == twice

    def test_current_region_reads_what_was_written(self) -> None:
        body = render_facts(SAMPLE)
        assert current_region(splice(document_with(), body)) == body


class TestMain:
    def _handoff(self, tmp_path: Path, body: str = "stale\n") -> Path:
        target = tmp_path / HANDOFF
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document_with(body), encoding="utf-8")
        return target

    def test_check_reports_a_stale_region_as_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exit 1 is the contract `--check` carries, so a scheduled job can act on it."""
        monkeypatch.setattr("refresh_handoff.collect_facts", lambda *_a, **_k: SAMPLE)
        self._handoff(tmp_path)
        assert main(["--check", "--root", str(tmp_path)]) == 1

    def test_check_writes_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("refresh_handoff.collect_facts", lambda *_a, **_k: SAMPLE)
        target = self._handoff(tmp_path)
        before = target.read_text(encoding="utf-8")
        main(["--check", "--root", str(tmp_path)])
        assert target.read_text(encoding="utf-8") == before

    def test_a_current_region_is_zero_and_leaves_the_file_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("refresh_handoff.collect_facts", lambda *_a, **_k: SAMPLE)
        target = self._handoff(tmp_path, body=render_facts(SAMPLE))
        before = target.read_text(encoding="utf-8")
        assert main(["--check", "--root", str(tmp_path)]) == 0
        assert target.read_text(encoding="utf-8") == before

    def test_refresh_writes_the_region(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("refresh_handoff.collect_facts", lambda *_a, **_k: SAMPLE)
        target = self._handoff(tmp_path)
        assert main(["--root", str(tmp_path)]) == 0
        assert render_facts(SAMPLE) in target.read_text(encoding="utf-8")

    def test_missing_markers_are_a_usage_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not a crash and not a success: the caller needs a distinct signal."""
        monkeypatch.setattr("refresh_handoff.collect_facts", lambda *_a, **_k: SAMPLE)
        target = tmp_path / HANDOFF
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# no markers here\n", encoding="utf-8")
        assert main(["--root", str(tmp_path)]) == 2

    def test_a_missing_handoff_is_a_usage_error(self, tmp_path: Path) -> None:
        assert main(["--root", str(tmp_path)]) == 2


class TestAgainstThisRepository:
    """The facts must be derivable from the real repository, not only a fixture."""

    def test_facts_are_collected_from_the_real_repository(self) -> None:
        facts = collect_facts(REPO_ROOT)
        assert facts.concepts > 0, "a concept count of zero is a bundle that was not read"
        assert facts.entries > 0, "an entry count of zero is a directory that was not read"
        assert facts.test_modules > 0
        assert facts.commit_types > 0

    def test_the_handoff_carries_the_markers_it_needs(self) -> None:
        """Without them the refresher refuses, so the scheduled job would no-op."""
        text = (REPO_ROOT / HANDOFF).read_text(encoding="utf-8")
        assert MARKER_START in text, "the handoff has no generated region"
        assert MARKER_END in text
        assert text.index(MARKER_START) < text.index(MARKER_END)

    def test_the_committed_region_is_current(self) -> None:
        """The whole point: what is on disk equals what the repository derives.

        This is the assertion the original design could not have satisfied — a region
        naming its own revision is stale the instant it is committed, so this would
        have failed on every commit, forever.
        """
        text = (REPO_ROOT / HANDOFF).read_text(encoding="utf-8")
        assert splice(text, render_facts(collect_facts(REPO_ROOT))) == text, (
            "the handoff's generated region is stale; run tools/refresh_handoff.py"
        )

    def test_the_real_region_is_not_invented(self) -> None:
        """What is in the region must be a rendering of the facts, not free text."""
        text = (REPO_ROOT / HANDOFF).read_text(encoding="utf-8")
        region = current_region(text).strip()
        assert region.startswith("| Fact | Value |"), "the region is not the generated table"
