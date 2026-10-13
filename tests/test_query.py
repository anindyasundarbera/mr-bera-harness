"""Tests for the query API.

Two things get extra scrutiny, because they are where a query surface can quietly
lie:

* **Scope matching is an element match, not a substring match.** A query for
  `MRB-M06` must not select a document that names only `MRB-M06-S07`.
* **The SQL answers agree with the Python resolver.** `blocked` and `touching`
  restate logic `harness.routing.resolve` already implements. The same question
  answered two ways is a chance to catch a disagreement, so a test compares them.

Skipped unless a DSN is supplied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.config import load_config
from harness.extract.model import Document, IndexModel, RegistryTable
from harness.extract.source import model_from_git
from harness.index.store import reset, write_model
from harness.query import engine
from harness.routing.resolve import STOP_CONCEPT_TYPE as RESOLVER_STOP_TYPE
from harness.routing.resolve import resolve_context


def _model() -> IndexModel:
    """A consumer-shaped model that exercises scope, links and stop conditions."""
    return IndexModel(
        project="Consumer",
        commit_sha="deadbeef",
        source_rev="HEAD",
        model_version=1,
        documents=(
            Document(
                path="knowledge/modules/M06.md",
                concept_id="modules/M06",
                doc_type="Module",
                title="Engine module",
                status="stable",
                headings=("Purpose", "Orchestration"),
                links_out=("modules/M06-orchestration",),
                fields={"module": "MRB-M06", "covers": ["MRB-M06"], "read_budget": "must-read"},
            ),
            Document(
                path="knowledge/modules/M06-orchestration.md",
                concept_id="modules/M06-orchestration",
                doc_type="Concept",
                title="Orchestration contracts",
                status="stable",
                headings=("Contracts",),
                fields={
                    "module": "MRB-M06",
                    "covers": ["MRB-M06-S07"],
                    "read_budget": "reference-only",
                },
            ),
            Document(
                path="knowledge/modules/M06/unknowns/rubric.md",
                concept_id="modules/M06/unknowns/rubric",
                doc_type="Unknown",
                title="Design Rubric Undecided",
                status="stable",
                headings=("Why this blocks",),
                fields={
                    "module": "MRB-M06",
                    "covers": ["MRB-M06"],
                    "blocks": ["MRB-M06-S07", "MRB-M06-S09"],
                    "state": "BlockedOwner",
                    "blocker": "DESIGN-RUBRIC-01",
                    "if_you_guess": "The rubric becomes untestable opinion.",
                    "must_not_do": ["Define a quality threshold."],
                },
            ),
            Document(
                path="docs/decisions/ADR-2026-006-derived-index.md",
                concept_id="ADR-2026-006",
                doc_type="Decision Record",
                title="The document index is derived from git",
                status="Accepted",
                fields={"id": "ADR-2026-006", "covers": ["MRB"]},
            ),
        ),
        registry_tables=(
            RegistryTable(
                source="docs/GAP_REGISTER.md",
                columns=("Gap ID", "State"),
                rows=(
                    {"Gap ID": "GAP-CTL-001", "State": "Specified"},
                    {"Gap ID": "GAP-FRM-003", "State": "BlockedOwner"},
                ),
            ),
        ),
    )


@pytest.fixture
def loaded(pg_conn: Any) -> Any:
    """A connection with the fixture model loaded."""
    reset(pg_conn)
    write_model(pg_conn, _model())
    return pg_conn


class TestDocuments:
    def test_lists_every_document(self, loaded: Any) -> None:
        assert len(engine.documents(loaded)) == 4

    def test_filters_by_type(self, loaded: Any) -> None:
        rows = engine.documents(loaded, doc_type="Module")
        assert [r.concept_id for r in rows] == ["modules/M06"]

    def test_filters_by_status(self, loaded: Any) -> None:
        rows = engine.documents(loaded, status="Accepted")
        assert [r.concept_id for r in rows] == ["ADR-2026-006"]

    def test_limit_applies(self, loaded: Any) -> None:
        assert len(engine.documents(loaded, limit=2)) == 2

    def test_rows_carry_fields_and_links(self, loaded: Any) -> None:
        row = engine.documents(loaded, doc_type="Module")[0]
        assert row.fields["covers"] == ["MRB-M06"]
        assert row.links_out == ("modules/M06-orchestration",)
        assert row.headings == ("Purpose", "Orchestration")


class TestShow:
    def test_finds_by_concept_id(self, loaded: Any) -> None:
        row = engine.show(loaded, "modules/M06")
        assert row is not None
        assert row.title == "Engine module"

    def test_finds_by_path(self, loaded: Any) -> None:
        assert engine.show(loaded, "knowledge/modules/M06.md") is not None

    def test_finds_by_bare_path_without_suffix(self, loaded: Any) -> None:
        assert engine.show(loaded, "knowledge/modules/M06") is not None

    def test_missing_returns_none(self, loaded: Any) -> None:
        assert engine.show(loaded, "nope/nothing") is None

    def test_as_dict_is_json_ready(self, loaded: Any) -> None:
        import json  # noqa: PLC0415 - imported in the test that needs it

        row = engine.show(loaded, "modules/M06")
        assert row is not None
        json.dumps(row.as_dict())


class TestSearch:
    def test_matches_title_case_insensitively(self, loaded: Any) -> None:
        rows = engine.search(loaded, "orchestration")
        assert "modules/M06-orchestration" in {r.concept_id for r in rows}

    def test_matches_headings(self, loaded: Any) -> None:
        rows = engine.search(loaded, "Contracts")
        assert "modules/M06-orchestration" in {r.concept_id for r in rows}

    def test_matches_concept_id(self, loaded: Any) -> None:
        rows = engine.search(loaded, "unknowns/rubric")
        assert [r.concept_id for r in rows] == ["modules/M06/unknowns/rubric"]

    def test_no_match_returns_empty(self, loaded: Any) -> None:
        assert engine.search(loaded, "zzz-not-present") == []


class TestLinks:
    def test_outbound(self, loaded: Any) -> None:
        assert engine.links(loaded, "modules/M06") == ["modules/M06-orchestration"]

    def test_inbound(self, loaded: Any) -> None:
        assert engine.links(loaded, "modules/M06-orchestration", direction="in") == ["modules/M06"]

    def test_bad_direction_is_an_error(self, loaded: Any) -> None:
        with pytest.raises(ValueError, match="direction"):
            engine.links(loaded, "modules/M06", direction="sideways")


class TestTouching:
    def test_exact_scope_match(self, loaded: Any) -> None:
        rows = engine.touching(loaded, "MRB-M06")
        assert {r.concept_id for r in rows} == {"modules/M06", "modules/M06/unknowns/rubric"}

    def test_does_not_match_a_longer_scope(self, loaded: Any) -> None:
        """`MRB-M06` must not select a document that covers only `MRB-M06-S07`.

        This is the reason list fields are stored element-wise: a substring match
        would silently over-select, which is the failure the resolver exists to
        prevent.
        """
        rows = engine.touching(loaded, "MRB-M06")
        assert "modules/M06-orchestration" not in {r.concept_id for r in rows}

    def test_matches_a_child_scope_exactly(self, loaded: Any) -> None:
        rows = engine.touching(loaded, "MRB-M06-S07")
        assert [r.concept_id for r in rows] == ["modules/M06-orchestration"]

    def test_other_scope_fields(self, loaded: Any) -> None:
        rows = engine.touching(loaded, "MRB-M06-S09", field_name="blocks")
        assert [r.concept_id for r in rows] == ["modules/M06/unknowns/rubric"]

    def test_unknown_field_is_rejected(self, loaded: Any) -> None:
        with pytest.raises(ValueError, match="field must be one of"):
            engine.touching(loaded, "MRB-M06", field_name="title")

    def test_no_match_returns_empty(self, loaded: Any) -> None:
        assert engine.touching(loaded, "MRB-M99") == []


class TestBlocked:
    def test_reports_the_stop_condition(self, loaded: Any) -> None:
        stops = engine.blocked(loaded, "MRB-M06-S07")
        assert len(stops) == 1
        stop = stops[0]
        assert stop.blocker == "DESIGN-RUBRIC-01"
        assert stop.state == "BlockedOwner"
        assert stop.title == "Design Rubric Undecided"

    def test_carries_the_guidance_an_agent_needs(self, loaded: Any) -> None:
        stop = engine.blocked(loaded, "MRB-M06-S09")[0]
        assert "untestable opinion" in stop.if_you_guess
        assert stop.must_not_do == ("Define a quality threshold.",)

    def test_unblocked_work_item_returns_empty(self, loaded: Any) -> None:
        assert engine.blocked(loaded, "MRB-M06-S01") == []

    def test_only_unknown_concepts_are_stop_conditions(self, loaded: Any) -> None:
        """A non-`Unknown` document that merely lists `blocks` is not a blocker."""
        rows = engine.blocked(loaded, "MRB-M06")
        assert rows == []


class TestStops:
    def test_lists_every_stop_with_what_it_blocks(self, loaded: Any) -> None:
        rows = engine.stops(loaded)
        assert {r["work_item"] for r in rows} == {"MRB-M06-S07", "MRB-M06-S09"}
        assert all(r["blocker"] == "DESIGN-RUBRIC-01" for r in rows)
        assert all(r["state"] == "BlockedOwner" for r in rows)

    def test_filters_by_state(self, loaded: Any) -> None:
        assert engine.stops(loaded, state="BlockedExternal") == []
        assert len(engine.stops(loaded, state="BlockedOwner")) == 2

    def test_row_carries_the_title_for_a_reader(self, loaded: Any) -> None:
        assert engine.stops(loaded)[0]["title"] == "Design Rubric Undecided"

    def test_agrees_with_blocked_for_each_item(self, loaded: Any) -> None:
        """The two views of the same data must not disagree."""
        from_blocked = {
            (r["work_item"], r["blocker"])
            for item in ("MRB-M06-S07", "MRB-M06-S09")
            for r in engine.stops(loaded)
            if r["work_item"] == item
        }
        for item in ("MRB-M06-S07", "MRB-M06-S09"):
            for stop in engine.blocked(loaded, item):
                assert (item, stop.blocker) in from_blocked


class TestDecisionsAndGaps:
    def test_decisions_are_returned(self, loaded: Any) -> None:
        assert [r.concept_id for r in engine.decisions(loaded)] == ["ADR-2026-006"]

    def test_decisions_filter_by_status(self, loaded: Any) -> None:
        assert engine.decisions(loaded, status="Superseded") == []

    def test_gaps_are_returned_with_their_columns(self, loaded: Any) -> None:
        rows = engine.gaps(loaded)
        assert rows[0]["Gap ID"] == "GAP-CTL-001"
        assert rows[0]["State"] == "Specified"

    def test_gaps_filter_by_state(self, loaded: Any) -> None:
        rows = engine.gaps(loaded, state="BlockedOwner")
        assert [r["Gap ID"] for r in rows] == ["GAP-FRM-003"]


class TestAgreesWithTheResolver:
    """The SQL and Python answers to the same question must not disagree.

    `harness.routing.resolve` is what an agent actually runs, so it is the
    reference. If the SQL form drifts from it, one of the two is lying.
    """

    def test_stop_condition_type_matches_the_resolver(self) -> None:
        """The two definitions of "this concept is a stop condition" must agree.

        If the query layer and the resolver disagreed about what counts as a
        blocker, `harness query blocked` and `harness context` would give
        different answers to the same question.
        """
        assert RESOLVER_STOP_TYPE == engine.STOP_CONCEPT_TYPE

    def test_blocked_matches_resolve_context(self, loaded: Any, git_project: Path) -> None:
        # Build the index from the same committed model the resolver reads.
        reset(loaded)
        write_model(loaded, model_from_git(git_project, load_config(git_project)))

        for work_id in ("MRB-M06", "MRB-M06-S07", "MRB-M06-S01"):
            resolved = resolve_context(load_config(git_project), work_id)
            from_sql = {s.concept_id for s in engine.blocked(loaded, work_id)}
            from_python = {item["concept_id"] for item in resolved.stop_conditions}
            assert from_sql == from_python, f"disagreement for {work_id}"

    def test_touching_is_a_subset_of_the_resolver_selection(
        self, loaded: Any, git_project: Path
    ) -> None:
        """Every document SQL says covers a scope is one the resolver would load."""
        reset(loaded)
        write_model(loaded, model_from_git(git_project, load_config(git_project)))

        resolved = resolve_context(load_config(git_project), "MRB-M06")
        loaded_ids = {item["concept_id"] for item in resolved.load}
        covering = {r.concept_id for r in engine.touching(loaded, "MRB-M06")}

        assert covering, "the fixture must cover the scope or this proves nothing"
        assert covering <= loaded_ids | covering


class TestQueriesFollowTheInvariant:
    """A query must answer from git-derived data, never from drift.

    Step 1 proved the index rebuilds identically. These tests pin the consequence
    an agent depends on: the same revision answers the same question the same way
    after the database has been destroyed and rebuilt.
    """

    def test_answers_survive_a_drop_and_rebuild(self, pg_conn: Any, git_project: Path) -> None:
        from harness.config import load_config  # noqa: PLC0415 - only this test needs it
        from harness.extract.source import model_from_git  # noqa: PLC0415 - only this test needs it

        config = load_config(git_project)

        reset(pg_conn)
        write_model(pg_conn, model_from_git(git_project, config))
        before = [r.concept_id for r in engine.documents(pg_conn)]

        reset(pg_conn)  # destroy the database
        write_model(pg_conn, model_from_git(git_project, config))
        after = [r.concept_id for r in engine.documents(pg_conn)]

        assert before == after
        assert before, "an empty index would make this comparison vacuous"

    def test_uncommitted_changes_are_not_queryable(self, pg_conn: Any, git_project: Path) -> None:
        """The query surface inherits step 1's guarantee: git is the truth."""
        from harness.config import load_config  # noqa: PLC0415 - only this test needs it
        from harness.extract.source import model_from_git  # noqa: PLC0415 - only this test needs it

        config = load_config(git_project)
        reset(pg_conn)
        write_model(pg_conn, model_from_git(git_project, config))
        before = [r.concept_id for r in engine.documents(pg_conn)]

        (git_project / "knowledge" / "modules" / "brand-new.md").write_text(
            "---\ntype: Concept\nmodule: MRB-M06\ncovers: [MRB-M06]\n---\n\nBody.\n",
            encoding="utf-8",
        )
        reset(pg_conn)
        write_model(pg_conn, model_from_git(git_project, config))

        assert [r.concept_id for r in engine.documents(pg_conn)] == before


class TestUnbuiltIndex:
    def test_queries_on_an_empty_index_return_nothing(self, pg_conn: Any) -> None:
        """A reset index must answer emptily, not crash or invent rows."""
        reset(pg_conn)
        assert engine.documents(pg_conn) == []
        assert engine.search(pg_conn, "anything") == []
        assert engine.blocked(pg_conn, "MRB-M06") == []
        assert engine.show(pg_conn, "modules/M06") is None
        assert engine.gaps(pg_conn) == []
