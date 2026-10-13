"""Tests for the derived PostgreSQL index store.

Skipped unless a DSN is supplied (`MRB_TEST_DSN`). The store is derived and
optional, so it must not be the reason CI fails on a machine with no database.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.extract.model import Document, IndexModel, RegistryTable, model_digest
from harness.index.store import (
    IndexUnavailableError,
    _redact,
    connect,
    read_model,
    reset,
    write_model,
)


def _model(**overrides: object) -> IndexModel:
    base: dict[str, object] = {
        "project": "Consumer",
        "commit_sha": "deadbeef",
        "source_rev": "HEAD",
        "model_version": 1,
        "documents": (
            Document(
                path="knowledge/a.md",
                concept_id="a",
                doc_type="Module",
                title="A",
                status="stable",
                headings=("Purpose", "Contracts"),
                links_out=("b",),
                fields={"module": "MRB-M06", "covers": ["MRB-M06", "MRB-M07"]},
            ),
            Document(
                path="knowledge/b.md",
                concept_id="b",
                doc_type="Concept",
                title="B",
                status="stable",
            ),
        ),
        "registry_tables": (
            RegistryTable(
                source="docs/GAP_REGISTER.md",
                columns=("Gap ID", "State"),
                rows=({"Gap ID": "G1", "State": "Open"}, {"Gap ID": "G2", "State": "BlockedOwner"}),
            ),
        ),
    }
    base.update(overrides)
    return IndexModel(**base)  # type: ignore[arg-type]


class TestDsnHandling:
    def test_missing_dsn_is_reported_not_guessed(self) -> None:
        with pytest.raises(IndexUnavailableError, match="no PostgreSQL DSN"):
            connect(None)

    def test_dsn_credentials_are_redacted(self) -> None:
        """A DSN must never reach a message or a log with its password."""
        assert _redact("postgresql://user:s3cret@localhost:5432/db") == (
            "postgresql://***@localhost:5432/db"
        )
        assert "s3cret" not in _redact("postgresql://user:s3cret@localhost/db")
        assert _redact("postgresql://localhost/db") == "postgresql://localhost/db"

    def test_redaction_survives_a_password_containing_an_at_sign(self) -> None:
        assert "s3cret" not in _redact("postgresql://user:p@ss@localhost/db")


class TestRoundTrip:
    def test_written_model_reads_back_byte_identical(self, pg_conn: Any) -> None:
        model = _model()
        write_model(pg_conn, model)
        assert model_digest(read_model(pg_conn)) == model_digest(model)

    def test_documents_survive_the_round_trip(self, pg_conn: Any) -> None:
        write_model(pg_conn, _model())
        read = read_model(pg_conn)
        by_id = {d.concept_id: d for d in read.documents}
        assert by_id["a"].headings == ("Purpose", "Contracts")
        assert by_id["a"].links_out == ("b",)
        assert by_id["a"].fields["covers"] == ["MRB-M06", "MRB-M07"]
        assert by_id["b"].fields == {}

    def test_registry_rows_survive_the_round_trip(self, pg_conn: Any) -> None:
        write_model(pg_conn, _model())
        table = read_model(pg_conn).registry_tables[0]
        assert table.columns == ("Gap ID", "State")
        assert table.rows[1] == {"Gap ID": "G2", "State": "BlockedOwner"}

    def test_a_row_with_only_empty_cells_still_round_trips(self, pg_conn: Any) -> None:
        """Row identity comes from the row table, not from the non-empty cells."""
        model = _model(
            registry_tables=(
                RegistryTable(source="r.md", columns=("A", "B"), rows=({"A": "", "B": ""},)),
            )
        )
        write_model(pg_conn, model)
        assert read_model(pg_conn).registry_tables[0].rows == ({"A": "", "B": ""},)

    def test_empty_model_round_trips(self, pg_conn: Any) -> None:
        model = _model(documents=(), registry_tables=())
        write_model(pg_conn, model)
        assert model_digest(read_model(pg_conn)) == model_digest(model)

    def test_read_model_of_an_empty_database_is_empty(self, pg_conn: Any) -> None:
        assert read_model(pg_conn).documents == ()

    def test_meta_records_provenance(self, pg_conn: Any) -> None:
        write_model(pg_conn, _model())
        read = read_model(pg_conn)
        assert read.commit_sha == "deadbeef"
        assert read.project == "Consumer"
        assert read.source_rev == "HEAD"

    def test_field_values_that_look_like_json_are_not_misread(self, pg_conn: Any) -> None:
        """A scalar beginning with `[` must not be silently parsed as a list."""
        model = _model(
            documents=(
                Document(
                    path="x.md",
                    concept_id="x",
                    doc_type="C",
                    title="X",
                    status="stable",
                    fields={"tags": "[not json"},
                ),
            )
        )
        write_model(pg_conn, model)
        assert read_model(pg_conn).documents[0].fields["tags"] == "[not json"


class TestDestroy:
    def test_reset_removes_everything(self, pg_conn: Any) -> None:
        write_model(pg_conn, _model())
        reset(pg_conn)
        assert read_model(pg_conn).documents == ()

    def test_write_is_idempotent_after_reset(self, pg_conn: Any) -> None:
        write_model(pg_conn, _model())
        reset(pg_conn)
        first = write_model(pg_conn, _model())
        reset(pg_conn)
        second = write_model(pg_conn, _model())
        assert first == second
