"""Deterministic extraction: committed bytes in, normalized model out.

No LLM, no clock, no network. The model this package produces is the only thing
the derived index is written from.
"""

from harness.extract.documents import (
    concept_document,
    extract_documents,
    extract_headings,
    extract_registry_tables,
    parse_markdown_tables,
    routing_fields,
)
from harness.extract.model import (
    MODEL_VERSION,
    ROUTING_FIELDS,
    Document,
    IndexModel,
    RegistryTable,
    model_digest,
)
from harness.extract.source import (
    IndexSourceError,
    commit_sha,
    materialize_commit,
    model_from_git,
    repo_root,
)

__all__ = [
    "MODEL_VERSION",
    "ROUTING_FIELDS",
    "Document",
    "IndexModel",
    "IndexSourceError",
    "RegistryTable",
    "commit_sha",
    "concept_document",
    "extract_documents",
    "extract_headings",
    "extract_registry_tables",
    "materialize_commit",
    "model_digest",
    "model_from_git",
    "parse_markdown_tables",
    "repo_root",
    "routing_fields",
]
