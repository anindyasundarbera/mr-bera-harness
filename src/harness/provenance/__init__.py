"""Link source code to the decision records that bind it.

Implements `ADR-2026-017`. A source file declares `harness:decision <ADR-ID>
sha256:<hex>`; the hex is the decision's **anchor digest** over its normative
content. Editing a decision therefore flags every file that implements it, which is
what makes the link checkable rather than a comment that rots.

Nothing here is inferred — a tool must not guess which decision produced a line of
code — and nothing here executes anything.
"""

from harness.provenance.checks import by_decision, render
from harness.provenance.links import (
    DIGEST_PREFIX_LENGTH,
    MARKER,
    NORMATIVE_FIELDS,
    Decision,
    Declaration,
    ProvenanceError,
    Report,
    decision_anchor_digest,
    declaration_for,
    declarations_in,
    load_decisions,
    scan,
)

__all__ = [
    "DIGEST_PREFIX_LENGTH",
    "MARKER",
    "NORMATIVE_FIELDS",
    "Declaration",
    "Decision",
    "ProvenanceError",
    "Report",
    "by_decision",
    "declaration_for",
    "declarations_in",
    "decision_anchor_digest",
    "load_decisions",
    "render",
    "scan",
]
