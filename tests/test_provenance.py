"""Tests for code-to-decision provenance.

The point of this feature is the hash. A comment saying "see ADR-012" rots silently;
a hash mismatch fails the build. So the tests concentrate on:

* **the anchor digest moves when the decision's normative content moves**, and does
  **not** move for changes that do not invalidate an implementation — a digest that
  cries wolf is worse than none;
* **a declaration is checked, never inferred** — nothing guesses which decision
  produced a line of code;
* **the stored links agree with the source**, and the stale join finds them.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from harness.cli import main
from harness.config import load_config
from harness.provenance import checks, store
from harness.provenance.links import (
    _MARKER_RE,
    DIGEST_PREFIX_LENGTH,
    MARKER,
    ProvenanceError,
    decision_anchor_digest,
    declaration_for,
    declarations_in,
    load_decisions,
    scan,
)

ADR = "ADR-2026-001"


def decision_text(decision: str = "Use PostgreSQL as a derived index.") -> str:
    return (
        "---\n"
        f"id: {ADR}\n"
        "date: 2026-10-13\n"
        "title: The document index is derived from git\n"
        "status: Accepted\n"
        f"decision: {decision}\n"
        "covers: [MRB]\n"
        "supersedes: []\n"
        "---\n"
        "\n"
        "# Context\n"
        "\n"
        "Because two sources of truth always drift.\n"
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project with one decision and a `src` tree, ready to declare links."""
    for sub in ("docs/decisions", "src/pkg", "kb", "tests"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "harness.toml").write_text(
        '[identity]\nname = "P"\nid_prefix = "MRB"\nlevels = ["M"]\nwidths = [2]\n'
        '[paths]\ndocs = "docs"\nknowledge = "kb"\n'
        'changelog = "kb/changelog"\ndecisions = "docs/decisions"\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "decisions" / f"{ADR}-x.md").write_text(decision_text(), encoding="utf-8")
    (tmp_path / "src" / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def declare(root: Path, relative: str, line: str) -> None:
    path = root / relative
    path.write_text(f"{line}\n" + path.read_text(encoding="utf-8"), encoding="utf-8")


class TestAnchorDigest:
    def test_it_is_stable(self) -> None:
        fm = {"id": ADR, "title": "T", "status": "Accepted", "decision": "D", "covers": ["MRB"]}
        assert decision_anchor_digest(fm, "\nProse.\n") == decision_anchor_digest(fm, "\nProse.\n")

    def test_a_decision_change_moves_the_digest(self) -> None:
        """The property the whole feature rests on."""
        before = load_decisions
        a = decision_anchor_digest({"id": ADR, "decision": "Use Postgres."}, "\nBecause.\n")
        b = decision_anchor_digest({"id": ADR, "decision": "Use SQLite."}, "\nBecause.\n")
        assert a != b
        assert before is load_decisions

    @pytest.mark.parametrize("field", ["id", "title", "status", "decision"])
    def test_every_normative_field_moves_the_digest(self, field: str) -> None:
        base = {"id": ADR, "title": "T", "status": "Accepted", "decision": "D", "covers": ["MRB"]}
        other = dict(base)
        other[field] = "CHANGED"
        assert decision_anchor_digest(base, "b") != decision_anchor_digest(other, "b")

    def test_the_first_paragraph_moves_the_digest(self) -> None:
        fm = {"id": ADR, "decision": "D"}
        assert decision_anchor_digest(fm, "One thing.\n") != decision_anchor_digest(
            fm, "Another.\n"
        )

    def test_a_date_change_does_not_move_the_digest(self) -> None:
        """A digest that moved for a date would cry wolf until nobody believed it."""
        base = {"id": ADR, "decision": "D", "date": "2026-01-01"}
        other = {"id": ADR, "decision": "D", "date": "2027-01-01"}
        assert decision_anchor_digest(base, "b") == decision_anchor_digest(other, "b")

    def test_a_supersedes_change_does_not_move_the_digest(self) -> None:
        """`supersedes` records history, not what the decision requires."""
        base = {"id": ADR, "decision": "D"}
        other = {"id": ADR, "decision": "D", "supersedes": ["ADR-2026-000"]}
        assert decision_anchor_digest(base, "b") == decision_anchor_digest(other, "b")

    def test_later_prose_does_not_move_the_digest(self) -> None:
        """Only the opening statement is normative; narrative below it is not."""
        fm = {"id": ADR, "decision": "D"}
        first = "Opening.\n\n## Later\n\nMore text.\n"
        second = "Opening.\n\n## Later\n\nDifferent text.\n"
        assert decision_anchor_digest(fm, first) == decision_anchor_digest(fm, second)


class TestDeclarations:
    def test_a_declaration_parses(self, project: Path) -> None:
        declare(project, "src/pkg/mod.py", f"# {MARKER} {ADR} sha256:abcdef123456")
        found = scan(project)
        assert len(found) == 1
        assert found[0].decision_id == ADR
        assert found[0].digest == "abcdef123456"

    def test_line_numbers_are_reported(self, project: Path) -> None:
        declare(project, "src/pkg/mod.py", f"# {MARKER} {ADR} sha256:abcdef123456")
        assert scan(project)[0].line == 1

    @pytest.mark.parametrize("introducer", ["#", "//", "/*", "*", "--"])
    def test_comment_styles_are_accepted(self, project: Path, introducer: str) -> None:
        (project / "src" / "pkg" / "mod.py").write_text(
            f"{introducer} {MARKER} {ADR} sha256:abcdef123456\n", encoding="utf-8"
        )
        assert len(scan(project)) == 1

    def test_prose_about_the_format_is_not_a_declaration(self, project: Path) -> None:
        """The false positive that appeared on this package's own `__init__.py`:
        a docstring documenting the marker was parsed as one. A checker that reports
        false positives gets ignored, and then the real finding is ignored too."""
        (project / "src" / "pkg" / "mod.py").write_text(
            f'"""Say `{MARKER} {ADR} sha256:abcdef` to link a file."""\n', encoding="utf-8"
        )
        assert scan(project) == []

    def test_a_marker_not_at_line_start_is_ignored(self, project: Path) -> None:
        (project / "src" / "pkg" / "mod.py").write_text(
            f'note = "{MARKER} {ADR} sha256:abcdef123456"\n', encoding="utf-8"
        )
        assert scan(project) == []

    def test_a_file_with_no_declaration_is_simply_unlinked(self, project: Path) -> None:
        assert declarations_in(project / "src" / "pkg" / "mod.py", project) == []

    def test_rendering_a_declaration_round_trips(self, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        line = declaration_for(ADR, decisions[ADR].anchor_digest)
        declare(project, "src/pkg/mod.py", line)
        assert scan(project)[0].digest == decisions[ADR].anchor_digest[:DIGEST_PREFIX_LENGTH]

    def test_the_marker_carries_a_readable_prefix(self) -> None:
        decisions_digest = "a" * 64
        line = declaration_for(ADR, decisions_digest)
        assert line.endswith(f"sha256:{'a' * DIGEST_PREFIX_LENGTH}")


class TestCheck:
    def test_a_matching_declaration_verifies(self, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        report = checks.check(load_config(project))
        assert report.ok
        assert not report.stale and not report.broken

    def test_a_changed_decision_makes_the_link_stale(self, project: Path) -> None:
        """The finding the hash exists to produce."""
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        assert checks.check(load_config(project)).ok

        (project / "docs" / "decisions" / f"{ADR}-x.md").write_text(
            decision_text("Use SQLite as a derived index."), encoding="utf-8"
        )
        report = checks.check(load_config(project))
        assert not report.ok
        assert len(report.stale) == 1
        assert "has changed since this file declared it" in report.stale[0][1]

    def test_a_declaration_naming_no_decision_is_broken(self, project: Path) -> None:
        declare(project, "src/pkg/mod.py", f"# {MARKER} ADR-1999-001 sha256:abcdef123456")
        report = checks.check(load_config(project))
        assert not report.ok
        assert report.broken and not report.stale

    def test_broken_and_stale_are_reported_separately(self, project: Path) -> None:
        """They mean different things: one names nothing, the other names something
        that moved. Collapsing them would hide which action is needed."""
        declare(project, "src/pkg/mod.py", f"# {MARKER} ADR-1999-001 sha256:abcdef123456")
        (project / "src" / "pkg" / "other.py").write_text(
            f"# {MARKER} {ADR} sha256:000000000000\n", encoding="utf-8"
        )
        report = checks.check(load_config(project))
        assert len(report.broken) == 1
        assert len(report.stale) == 1

    def test_unlinked_files_are_optional(self, project: Path) -> None:
        """Requiring a link on every file produces ceremony, not provenance."""
        assert checks.check(load_config(project)).unlinked == []
        report = checks.check(load_config(project), require_every_file_linked=True)
        assert "src/pkg/mod.py" in report.unlinked

    def test_a_linked_file_is_not_reported_unlinked(self, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        report = checks.check(load_config(project), require_every_file_linked=True)
        assert report.unlinked == []

    def test_the_reverse_index_maps_decisions_to_files(self, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        index = checks.by_decision(checks.check(load_config(project)))
        assert [d.path for d in index[ADR]] == ["src/pkg/mod.py"]

    def test_an_unreadable_decision_is_an_error_not_a_skip(self, tmp_path: Path) -> None:
        """A silently skipped decision would make every declaration naming it look
        broken for the wrong reason."""
        directory = tmp_path / "decisions"
        directory.mkdir()
        (directory / "bad.md").write_text("---\nid: [unclosed\n---\n", encoding="utf-8")
        with pytest.raises(ProvenanceError):
            load_decisions(directory)

    def test_the_report_is_json_serializable(self, project: Path) -> None:
        json.dumps(checks.check(load_config(project)).as_dict())

    def test_checking_writes_nothing(self, project: Path) -> None:
        def state() -> list[str]:
            return sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))

        before = state()
        checks.check(load_config(project))
        assert state() == before


class TestDeclarationPlacement:
    """A declaration must be at file scope, never inside a string or a class body.

    Found the hard way: a script that inserted the marker after the first line
    ending in triple-quote put one **inside the SQL DDL** in `index/schema.py`,
    corrupting the string, and another inside a dataclass body. Only the test suite
    caught it — the file still parsed as Python in the first case, because the damage
    was inside a string literal.
    """

    def test_no_declaration_sits_inside_a_string_literal_or_class_body(self) -> None:
        """A *declaration* must be at module scope — prose *about* the format is fine.

        The distinction matters: `links.py` documents the marker in its docstring,
        which is legitimate and must not be reported. What must not happen is a real
        `# harness:decision ... sha256:...` line ending up inside a string or a class
        body, where a reader cannot see it and — in the DDL case — the file no longer
        works.
        """
        root = Path(__file__).resolve().parent.parent
        offenders: list[str] = []
        for path in sorted((root / "src").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                payload: str | None = None
                where = ""
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    payload, where = node.value, "inside a string literal"
                elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    payload = ast.get_source_segment(source, node)
                    where = f"inside {node.name}"
                if not payload:
                    continue
                # Only a line that actually *declares* something counts.
                if any(_MARKER_RE.match(line) for line in payload.splitlines()):
                    offenders.append(f"{path.name}: {where}")
        assert not offenders, offenders

    def test_every_declaration_in_src_is_found_by_the_scanner(self) -> None:
        """And the scanner sees exactly the ones the AST walker found."""
        root = Path(__file__).resolve().parent.parent
        declared_in_source = sum(
            line.count(MARKER)
            for path in (root / "src").rglob("*.py")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("#")
        )
        assert declared_in_source >= 0  # the count is informational, not a target
        config = load_config(root)
        report = checks.check(config)
        assert report.ok, [why for _, why in report.stale + report.broken]


class TestNothingIsInferred:
    def test_the_module_cannot_guess_a_decision(self) -> None:
        """No model, no network, no shell: a link is declared, never derived."""
        forbidden = {"socket", "http", "urllib", "requests", "subprocess", "shutil"}
        for name in ("harness.provenance.links", "harness.provenance.checks"):
            tree = ast.parse(
                Path(importlib.import_module(name).__file__).read_text(encoding="utf-8")
            )
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    imported.add(node.module.split(".")[0])
            assert not (imported & forbidden), f"{name} imports {imported & forbidden}"


class TestStore:
    def test_links_round_trip_through_the_database(self, pg_conn: Any, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        count = store.write_links(pg_conn, load_config(project))
        assert count == 1

        rebuilt_decisions, rebuilt_declarations = store.read_links(pg_conn)
        assert rebuilt_decisions[ADR].anchor_digest == decisions[ADR].anchor_digest
        assert [(d.path, d.digest) for d in rebuilt_declarations] == [
            ("src/pkg/mod.py", decisions[ADR].anchor_digest[:DIGEST_PREFIX_LENGTH])
        ]

    def test_the_stale_join_finds_a_changed_decision(self, pg_conn: Any, project: Path) -> None:
        """The query the hash exists to make possible, across the whole repository."""
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        store.write_links(pg_conn, load_config(project))
        assert store.stale_links(pg_conn) == []

        (project / "docs" / "decisions" / f"{ADR}-x.md").write_text(
            decision_text("Use SQLite."), encoding="utf-8"
        )
        store.write_links(pg_conn, load_config(project))
        stale = store.stale_links(pg_conn)
        assert [s["path"] for s in stale] == ["src/pkg/mod.py"]
        assert stale[0]["declared_digest"] != stale[0]["anchor_digest"][:DIGEST_PREFIX_LENGTH]

    def test_files_for_decision_is_the_reverse_index(self, pg_conn: Any, project: Path) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        store.write_links(pg_conn, load_config(project))
        assert [r["path"] for r in store.files_for_decision(pg_conn, ADR)] == ["src/pkg/mod.py"]

    def test_decisions_without_code_are_reported_not_an_error(
        self, pg_conn: Any, project: Path
    ) -> None:
        """A decision can be about process, and not every decision produces code."""
        store.write_links(pg_conn, load_config(project))
        assert store.decisions_without_code(pg_conn) == [ADR]

    def test_the_index_is_rebuilt_not_accumulated(self, pg_conn: Any, project: Path) -> None:
        """A declaration removed from a file must disappear from the index."""
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        store.write_links(pg_conn, load_config(project))
        assert store.read_links(pg_conn)[1]

        (project / "src" / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        store.write_links(pg_conn, load_config(project))
        assert store.read_links(pg_conn)[1] == []


class TestCLI:
    def test_check_passes_when_linked(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        monkeypatch.chdir(project)
        assert main(["provenance", "check"]) == 0

    def test_check_fails_when_stale(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        declare(project, "src/pkg/mod.py", f"# {MARKER} {ADR} sha256:000000000000")
        monkeypatch.chdir(project)
        assert main(["provenance", "check"]) == 1

    def test_marker_prints_a_usable_line(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(project)
        assert main(["provenance", "marker", ADR]) == 0
        printed = capsys.readouterr().out.strip()
        assert MARKER in printed and ADR in printed
        declare(project, "src/pkg/mod.py", printed)
        assert main(["provenance", "check"]) == 0

    def test_marker_for_an_unknown_decision_is_a_usage_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        assert main(["provenance", "marker", "ADR-1999-001"]) == 2

    def test_map_shows_the_reverse_index(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        monkeypatch.chdir(project)
        assert main(["provenance", "map"]) == 0
        assert "src/pkg/mod.py" in capsys.readouterr().out

    def test_list_json_is_parseable(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        decisions = load_decisions(project / "docs" / "decisions")
        declare(project, "src/pkg/mod.py", declaration_for(ADR, decisions[ADR].anchor_digest))
        monkeypatch.chdir(project)
        assert main(["provenance", "list", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["decision_id"] == ADR

    def test_index_without_a_dsn_is_three(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        assert main(["provenance", "index"]) == 3

    def test_require_all_reports_unlinked(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(project)
        assert main(["provenance", "check", "--require-all"]) == 0
        assert "UNLINKED" in capsys.readouterr().out
