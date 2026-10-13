"""Tests for the normalized model and its digest.

The digest is the invariant's equality function, so it gets the scrutiny: it must
change when content changes and must not change when only ordering or formatting
of the source changes.
"""

from __future__ import annotations

import json

from harness.extract.model import Document, IndexModel, RegistryTable, model_digest


def _model(**overrides: object) -> IndexModel:
    base: dict[str, object] = {
        "project": "P",
        "commit_sha": "abc",
        "source_rev": "HEAD",
        "model_version": 1,
        "documents": (
            Document(path="a.md", concept_id="a", doc_type="Module", title="A", status="stable"),
        ),
        "registry_tables": (),
    }
    base.update(overrides)
    return IndexModel(**base)  # type: ignore[arg-type]


class TestDigest:
    def test_digest_is_stable_for_the_same_model(self) -> None:
        assert model_digest(_model()) == model_digest(_model())

    def test_digest_changes_when_a_document_is_added(self) -> None:
        assert model_digest(_model()) != model_digest(
            _model(
                documents=(
                    Document(
                        path="a.md", concept_id="a", doc_type="Module", title="A", status="stable"
                    ),
                    Document(
                        path="b.md", concept_id="b", doc_type="Concept", title="B", status="stable"
                    ),
                )
            )
        )

    def test_digest_ignores_document_order(self) -> None:
        """Ordering is a filesystem artifact, not content, so it must not matter."""
        a = Document(path="a.md", concept_id="a", doc_type="Module", title="A", status="stable")
        b = Document(path="b.md", concept_id="b", doc_type="Concept", title="B", status="stable")
        assert model_digest(_model(documents=(a, b))) == model_digest(_model(documents=(b, a)))

    def test_digest_changes_when_a_field_changes(self) -> None:
        one = Document(
            path="a.md",
            concept_id="a",
            doc_type="Module",
            title="A",
            status="stable",
            fields={"module": "MRB-M06"},
        )
        two = Document(
            path="a.md",
            concept_id="a",
            doc_type="Module",
            title="A",
            status="stable",
            fields={"module": "MRB-M07"},
        )
        assert model_digest(_model(documents=(one,))) != model_digest(_model(documents=(two,)))

    def test_digest_of_empty_models_is_equal(self) -> None:
        """An honest limitation: two empty models are indistinguishable by digest.

        A test that only compared empty models would pass vacuously, which is why
        the invariant test also asserts the model is non-empty.
        """
        assert model_digest(_model(documents=(), registry_tables=())) == model_digest(
            _model(documents=(), registry_tables=())
        )

    def test_digest_covers_registry_tables(self) -> None:
        table = RegistryTable(
            source="docs/G.md",
            columns=("Gap ID", "State"),
            rows=({"Gap ID": "G1", "State": "Open"},),
        )
        assert model_digest(_model(documents=(), registry_tables=(table,))) != model_digest(
            _model(documents=(), registry_tables=())
        )


class TestCanonical:
    def test_canonical_sorts_documents_and_tables(self) -> None:
        model = _model(
            documents=(
                Document(path="b.md", concept_id="b", doc_type="C", title="B", status="stable"),
                Document(path="a.md", concept_id="a", doc_type="C", title="A", status="stable"),
            ),
            registry_tables=(
                RegistryTable(source="z.md", columns=("a",)),
                RegistryTable(source="a.md", columns=("a",)),
            ),
        )
        canonical = model.to_canonical()
        assert [d["path"] for d in canonical["documents"]] == ["a.md", "b.md"]
        assert [t["source"] for t in canonical["registry_tables"]] == ["a.md", "z.md"]

    def test_canonical_is_json_serializable(self) -> None:
        json.dumps(_model().to_canonical())
