"""Deterministic query surface over the derived index.

Build-order step 2 of `HARNESS_ARCHITECTURE.md` §9: the lookup surface that
replaces file-reading. Pure code reading a derived store, so a query costs no
tokens and cannot hallucinate.
"""

from harness.query.engine import (
    SCOPE_FIELDS,
    STOP_CONCEPT_TYPE,
    Blocked,
    Row,
    blocked,
    decisions,
    documents,
    gaps,
    links,
    search,
    show,
    stops,
    touching,
)

__all__ = [
    "SCOPE_FIELDS",
    "STOP_CONCEPT_TYPE",
    "Blocked",
    "Row",
    "blocked",
    "decisions",
    "documents",
    "gaps",
    "links",
    "search",
    "show",
    "stops",
    "touching",
]
