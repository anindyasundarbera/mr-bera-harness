"""The normalized document model produced by extraction.

This model is the artefact the index is written from and compared against. It is
deliberately dumb: frozen dataclasses carrying only what can be read from
committed bytes. It holds no timestamps, no row ids and no insertion order, so a
model built from the same git revision always serializes to the same bytes —
which is what makes the rebuild invariant provable rather than aspirational.

`model_digest` is the equality function the invariant test uses. It hashes a
canonical JSON rendering with sorted keys and LF line endings, so two models are
"identical" only when their content is identical.
"""

# harness:decision ADR-2026-006 sha256:66679384f7b7

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: Bumped whenever the shape below changes, so a stale index can be told apart
#: from a current one without guessing.
MODEL_VERSION = 1

#: Frontmatter keys that are routing facts and therefore belong in the index.
#: Anything else is left in the document, not duplicated into the index, so the
#: index cannot become a second place where a fact is authored.
ROUTING_FIELDS = (
    "module",
    "class",
    "covers",
    "depends_on",
    "do_not_use_for",
    "read_budget",
    "blocks",
    "state",
    "blocker",
    "tags",
    "id",
)


@dataclass(frozen=True)
class Document:
    """One markdown document and the routable facts extracted from it."""

    path: str
    concept_id: str
    doc_type: str
    title: str
    status: str
    #: Body headings, in document order (text only, no leading `#`).
    headings: tuple[str, ...] = ()
    #: Internal link targets, resolved to bundle-relative concept ids.
    links_out: tuple[str, ...] = ()
    #: Routing facts from frontmatter, string- or list-valued.
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistryTable:
    """A markdown table extracted from a registry document."""

    source: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class IndexModel:
    """The complete extracted model for one git revision.

    `commit_sha` and `source_rev` record provenance — which commit the model was
    read from — so an index always states where it came from.
    """

    project: str
    commit_sha: str
    source_rev: str
    model_version: int
    documents: tuple[Document, ...] = ()
    registry_tables: tuple[RegistryTable, ...] = ()

    def to_canonical(self) -> dict[str, Any]:
        """A stable, JSON-safe dict. Documents are sorted by path.

        Sorting here rather than relying on walk order is what makes the digest
        independent of the filesystem's enumeration order.
        """
        documents = sorted(self.documents, key=lambda d: d.path)
        tables = sorted(self.registry_tables, key=lambda t: t.source)
        return {
            "project": self.project,
            "commit_sha": self.commit_sha,
            "source_rev": self.source_rev,
            "model_version": self.model_version,
            "documents": [
                {
                    **asdict(doc),
                    "headings": list(doc.headings),
                    "links_out": list(doc.links_out),
                    "fields": doc.fields,
                }
                for doc in documents
            ],
            "registry_tables": [
                {
                    "source": table.source,
                    "columns": list(table.columns),
                    "rows": [dict(row) for row in table.rows],
                }
                for table in tables
            ],
        }


def model_digest(model: IndexModel) -> str:
    """SHA-256 over the canonical rendering of a model.

    Sorted keys and no whitespace variance mean the digest changes if and only
    if the content changes. Callers must never compare models by `==` in the
    invariant test: a dataclass comparison would pass on any two empty models.
    """
    payload = json.dumps(
        model.to_canonical(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
