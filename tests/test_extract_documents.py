"""Tests for document, heading, link and markdown-table extraction.

All fixtures are consumer projects with a *different* layout from the harness's
own, so a passing test cannot be a coincidence of reading the wrong repository.
"""

from __future__ import annotations

from pathlib import Path

from harness.extract.documents import (
    extract_documents,
    extract_headings,
    parse_markdown_tables,
    routing_fields,
)
from harness.okf import Bundle


class TestHeadings:
    def test_collects_headings_in_order(self) -> None:
        body = "# One\n\ntext\n\n## Two\n\n### Three\n"
        assert extract_headings(body) == ("One", "Two", "Three")

    def test_ignores_headings_inside_fenced_code(self) -> None:
        body = "# Real\n\n```python\n# not a heading\n```\n\n## Also real\n"
        assert extract_headings(body) == ("Real", "Also real")

    def test_strips_trailing_hashes(self) -> None:
        assert extract_headings("## Title ##\n") == ("Title",)

    def test_empty_body_yields_nothing(self) -> None:
        assert extract_headings("") == ()


class TestRoutingFields:
    def test_keeps_only_routing_keys(self) -> None:
        fields = routing_fields({"module": "MRB-M06", "title": "T", "decision_status": "x"})
        assert fields == {"module": "MRB-M06"}

    def test_stringifies_scalars_and_lists(self) -> None:
        fields = routing_fields({"module": "MRB-M06", "covers": ["MRB-M06", "MRB-M07"]})
        assert fields["covers"] == ["MRB-M06", "MRB-M07"]

    def test_drops_none_values(self) -> None:
        assert "state" not in routing_fields({"state": None})


class TestMarkdownTables:
    def test_parses_header_and_rows(self) -> None:
        text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        tables = parse_markdown_tables(text)
        assert len(tables) == 1
        columns, rows = tables[0]
        assert columns == ("A", "B")
        assert rows[0] == {"A": "1", "B": "2"}
        assert len(rows) == 2

    def test_column_identity_comes_from_the_header_not_position(self) -> None:
        """A register whose column order changes must not silently shift meaning."""
        text = "| State | Gap ID |\n|---|---|\n| BlockedOwner | GAP-X-001 |\n"
        _, rows = parse_markdown_tables(text)[0]
        assert rows[0]["State"] == "BlockedOwner"
        assert rows[0]["Gap ID"] == "GAP-X-001"

    def test_ignores_a_table_without_a_separator_row(self) -> None:
        assert parse_markdown_tables("| A | B |\n| 1 | 2 |\n") == []

    def test_ignores_prose_pipes(self) -> None:
        assert parse_markdown_tables("this | is | prose\n") == []

    def test_parses_two_separate_tables(self) -> None:
        text = "| A |\n|---|\n| 1 |\n\ntext\n\n| B |\n|---|\n| 2 |\n"
        tables = parse_markdown_tables(text)
        assert [t[0] for t in tables] == [("A",), ("B",)]

    def test_pads_short_rows(self) -> None:
        text = "| A | B |\n|---|---|\n| 1 |\n"
        _, rows = parse_markdown_tables(text)[0]
        assert rows[0] == {"A": "1", "B": ""}

    def test_row_with_all_cells_empty_is_kept(self) -> None:
        text = "| A | B |\n|---|---|\n|  |  |\n"
        _, rows = parse_markdown_tables(text)[0]
        assert rows == ({"A": "", "B": ""},)

    def test_handles_a_leading_pipe_absent_form(self) -> None:
        assert parse_markdown_tables("A | B\n---|---\n1 | 2\n") == []


class TestExtractDocuments:
    def test_extracts_type_title_status_and_headings(self, git_project: Path) -> None:
        bundle = Bundle(git_project / "knowledge")
        documents = extract_documents(bundle, git_project)
        by_id = {d.concept_id: d for d in documents}
        engine = by_id["modules/M06-engine"]
        assert engine.doc_type == "Module"
        assert engine.status == "stable"
        assert engine.headings == ("Purpose",)
        assert engine.fields["module"] == "MRB-M06"

    def test_resolves_internal_links_to_concept_ids(self, git_project: Path) -> None:
        bundle = Bundle(git_project / "knowledge")
        by_id = {d.concept_id: d for d in extract_documents(bundle, git_project)}
        assert "modules/M06-orchestration" in by_id["modules/M06-engine"].links_out

    def test_ignores_external_links(self, git_project: Path) -> None:
        path = git_project / "knowledge" / "modules" / "ext.md"
        path.write_text(
            "---\ntype: Concept\nmodule: MRB-M06\ncovers: [MRB-M06]\n---\n\n"
            "See [docs](https://example.com/x.md).\n",
            encoding="utf-8",
        )
        by_id = {
            d.concept_id: d
            for d in extract_documents(Bundle(git_project / "knowledge"), git_project)
        }
        assert by_id["modules/ext"].links_out == ()

    def test_documents_are_ordered_by_path(self, git_project: Path) -> None:
        paths = [d.path for d in extract_documents(Bundle(git_project / "knowledge"), git_project)]
        assert paths == sorted(paths)
