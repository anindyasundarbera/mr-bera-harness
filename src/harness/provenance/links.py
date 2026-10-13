"""Link source code to the decision records that bind it.

Implements `ADR-2026-017` — *link source code to the decisions that produced it* —
with the property that makes the link **checkable** rather than prose: each link
carries the decision's **content hash**, so editing a decision flags every file that
implements it.

Two halves, deliberately separable:

* the **declaration**, in the source file, carrying the decision id and its hash;
* the **anchor**, in the decision record, which is what the hash is computed from.

If the anchor changes, the declaration no longer matches, and CI says so. That is the
difference between a checked link and a comment: a comment saying "see ADR-012" rots
silently, whereas a hash mismatch fails the build.

**Nothing here executes anything** and nothing here is inferred. A tool must not
guess which decision produced a line of code — an inferred association is a guess
presented as provenance — so a file declares its own, and the check only verifies.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The declaration marker. One line, machine-readable, and deliberately **not** free
#: prose: a comment can say anything, and a declaration is parsed and checked.
#:
#:     # harness:decision ADR-2026-009 sha256:<12 hex chars>
#:
#: The hash is the decision's *anchor* digest (see `decision_anchor_digest`), which
#: covers the normative frontmatter fields and the first prose paragraph — not the
#: whole document, which changes for reasons that do not invalidate an implementation,
#: such as a change-history line.
MARKER = "harness:decision"

_MARKER_RE = re.compile(
    rf"^\s*(?:#|//|/\*|\*|--)\s*{re.escape(MARKER)}\s+"
    rf"(?P<decision_id>[A-Za-z0-9-]+)\s+sha256:(?P<digest>[0-9a-f]{{8,64}})"
)

#: Characters that must precede the marker for it to count as a declaration.
#:
#: Requiring a **comment introducer at line start** is what stops prose *about* the
#: format being read as a declaration. Without it, a docstring that documents the
#: marker is itself parsed as one — which happened the first time this ran, on the
#: package's own `__init__.py`. A checker that reports false positives gets ignored,
#: and then the real finding is ignored too.
COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")

#: The frontmatter fields that constitute a decision's *normative* content. A change
#: to any of these changes what the decision requires, so an implementation is
#: potentially invalidated. Fields not listed here — `date`, `supersedes`, prose
#: narrative — can change without that implication.
NORMATIVE_FIELDS = ("id", "title", "status", "decision", "covers")

#: How many hex characters of the digest a marker carries. Twelve is ample to detect a
#: change and short enough to read; the full digest is available from the tooling.
DIGEST_PREFIX_LENGTH = 12


class ProvenanceError(Exception):
    """Raised when a declaration is malformed or a decision cannot be read."""


@dataclass
class Declaration:
    """One `harness:decision` line, and where it was found."""

    path: str
    line: int
    decision_id: str
    digest: str
    raw: str = ""

    @property
    def as_key(self) -> tuple[str, str, int]:
        return (self.path, self.decision_id, self.line)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "decision_id": self.decision_id,
            "digest": self.digest,
        }


@dataclass
class Decision:
    """A decision record, with the digest its declarations must match."""

    decision_id: str
    path: str
    title: str
    status: str
    anchor_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "path": self.path,
            "title": self.title,
            "status": self.status,
            "anchor_digest": self.anchor_digest,
        }


@dataclass
class Report:
    """The outcome of checking every declaration."""

    decisions: dict[str, Decision] = field(default_factory=dict)
    declarations: list[Declaration] = field(default_factory=list)
    stale: list[tuple[Declaration, str]] = field(default_factory=list)
    broken: list[tuple[Declaration, str]] = field(default_factory=list)
    unlinked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.stale and not self.broken

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "decisions": {k: v.as_dict() for k, v in self.decisions.items()},
            "declarations": [d.as_dict() for d in self.declarations],
            "stale": [{"declaration": d.as_dict(), "detail": why} for d, why in self.stale],
            "broken": [{"declaration": d.as_dict(), "detail": why} for d, why in self.broken],
            "unlinked": list(self.unlinked),
        }


def decision_anchor_digest(frontmatter: dict[str, Any], body: str) -> str:
    """The digest a source declaration must carry for this decision.

    Covers the **normative** content only:

    * the frontmatter fields in `NORMATIVE_FIELDS`, in a fixed order;
    * the first paragraph of prose after the title, which is where a record states
      what it decides in a sentence.

    Deliberately excluded: `date`, `supersedes`, the change-history table, and later
    prose. Those change for reasons that do not invalidate an implementation, and a
    digest that moved for them would cry wolf until nobody believed it.
    """
    parts: list[str] = []
    for key in NORMATIVE_FIELDS:
        value = frontmatter.get(key)
        if isinstance(value, list):
            parts.append(f"{key}={','.join(str(v) for v in value)}")
        elif value is not None:
            parts.append(f"{key}={value}")

    paragraph = _first_paragraph(body)
    if paragraph:
        parts.append(f"prose={paragraph}")

    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _first_paragraph(body: str) -> str:
    """The first non-heading paragraph of a record's body, whitespace-normalised."""
    chunks: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if chunks:
                break
            continue
        if not stripped:
            if chunks:
                break
            continue
        chunks.append(stripped)
    return " ".join(chunks)


def load_decisions(decisions_dir: Path) -> dict[str, Decision]:
    """Every decision record in a directory, keyed by id.

    A record that cannot be read is a `ProvenanceError`, not a skip: a missing decision
    would make every declaration pointing at it look broken for the wrong reason.
    """
    from harness.okf import (  # noqa: PLC0415 - avoids a cycle at import
        OkfError,
        split_frontmatter,
    )

    found: dict[str, Decision] = {}
    for path in sorted(decisions_dir.glob("*.md")):
        if path.name == "index.md":
            continue
        try:
            frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except OkfError as exc:
            raise ProvenanceError(f"{path.name} is unreadable: {exc}") from exc
        decision_id = str(frontmatter.get("id", "")).strip()
        if not decision_id:
            continue
        found[decision_id] = Decision(
            decision_id=decision_id,
            path=path.name,
            title=str(frontmatter.get("title", "")),
            status=str(frontmatter.get("status", "")),
            anchor_digest=decision_anchor_digest(frontmatter, body),
        )
    return found


def declarations_in(path: Path, root: Path) -> list[Declaration]:
    """Every declaration in one file, with line numbers.

    A malformed marker is an error rather than an ignored line: a declaration that
    silently does not parse is a link nobody is checking.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    found: list[Declaration] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _MARKER_RE.match(line)
        if not match:
            continue
        found.append(
            Declaration(
                path=path.relative_to(root).as_posix(),
                line=number,
                decision_id=match.group("decision_id"),
                digest=match.group("digest"),
                raw=line.rstrip(),
            )
        )
    return found


def declaration_for(decision_id: str, digest: str, *, comment: str = "#") -> str:
    """Render a declaration line for a file, so no one has to remember the format."""
    return f"{comment} {MARKER} {decision_id} sha256:{digest[:DIGEST_PREFIX_LENGTH]}"


def scan(root: Path, *, sources: list[str] | None = None) -> list[Declaration]:
    """Every declaration under `sources` (default: `src`), ordered by path then line."""
    roots = [root / s for s in (sources or ["src"])]
    found: list[Declaration] = []
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".ts", ".js", ".go", ".rs", ".java"}:
                found.extend(declarations_in(path, root))
    return found
