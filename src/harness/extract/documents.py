"""Parse documents, markdown tables and links into the normalized model.

Parsing is *reused*, not reimplemented: this module sits on top of
`harness.okf.reader` (`Bundle`, `Concept`, `split_frontmatter`), which is already
OKF-conformant and tested. What this module adds is the small amount of shape
that an index needs — routable frontmatter fields, body headings, resolved link
targets, and registry markdown tables.

Everything here is a pure function of the text it is given. It never resolves a
path from its own location and never reads the clock, so the same bytes always
produce the same model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harness.extract.model import ROUTING_FIELDS, Document, RegistryTable
from harness.okf import Bundle, Concept

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
# A table's separator row: pipes, dashes, colons and spaces only, at least one dash.
_TABLE_SEP_RE = re.compile(r"^\|?[ \t]*:?-{1,}:?[ \t]*(\|[ \t]*:?-{1,}:?[ \t]*)*\|?[ \t]*$")


def extract_headings(body: str) -> tuple[str, ...]:
    """Body headings in document order, text only.

    Fenced code is skipped so a `# comment` inside an example is not mistaken
    for a heading. The fence state is tracked rather than guessed.
    """
    headings: list[str] = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append(match.group(2).strip())
    return tuple(headings)


def _coerce(value: Any) -> Any:
    """Reduce a frontmatter value to a stable, index-friendly scalar or list."""
    if isinstance(value, list):
        return [str(v) if not isinstance(v, dict) else json.dumps(v, sort_keys=True) for v in value]
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def routing_fields(frontmatter: dict[str, Any]) -> dict[str, Any]:
    """The routing facts from frontmatter, in a fixed key order.

    Only keys in `ROUTING_FIELDS` are indexed. Indexing arbitrary frontmatter
    would duplicate the document into the index and invite the index to become a
    second place a fact is authored.
    """
    return {
        key: _coerce(frontmatter[key])
        for key in ROUTING_FIELDS
        if key in frontmatter and frontmatter[key] is not None
    }


def parse_markdown_tables(text: str) -> list[tuple[tuple[str, ...], tuple[dict[str, str], ...]]]:
    """Parse every markdown table in a document.

    A table is a header row followed by a separator row. Column identity is
    taken from the header — never position — so a register whose column order
    changes does not silently shift which value a column means.
    """
    lines = text.splitlines()
    tables: list[tuple[tuple[str, ...], tuple[dict[str, str], ...]]] = []
    index = 0
    while index < len(lines):
        header = _split_row(lines[index])
        if header is None or index + 1 >= len(lines):
            index += 1
            continue
        if not _TABLE_SEP_RE.match(lines[index + 1].strip()):
            index += 1
            continue

        columns = tuple(header)
        rows: list[dict[str, str]] = []
        cursor = index + 2
        while cursor < len(lines) and (cells := _split_row(lines[cursor])) is not None:
            padded = cells + [""] * (len(columns) - len(cells))
            rows.append({col: padded[i] for i, col in enumerate(columns)})
            cursor += 1
        tables.append((columns, tuple(rows)))
        index = cursor
    return tables


def _split_row(line: str) -> list[str] | None:
    """Split a table row into cells, or None when the line is not a row."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    inner = stripped.strip("|")
    return [cell.strip() for cell in inner.split("|")]


def concept_document(concept: Concept, bundle: Bundle, root: Path) -> Document:
    """Build a `Document` from one OKF concept.

    Two identifiers, each with one meaning:

    * `path` is root-relative, so the file can be located in git.
    * `concept_id` is the OKF bundle-relative id (`Concept.concept_id`), so the
      index joins to the routing layer on the identifier that layer already uses
      rather than inventing a second one. Links are resolved to the same space,
      which makes the link graph joinable on `concept_id`.
    """
    resolved_root = root.resolve()
    resolved_bundle = bundle.root.resolve()
    rel = concept.path.resolve().relative_to(resolved_root).as_posix()

    links: list[str] = []
    for raw in concept.links():
        target = bundle.resolve_path(concept, raw)
        if target is None:  # a URL, not an internal link
            continue
        try:
            links.append(target.resolve().relative_to(resolved_bundle).with_suffix("").as_posix())
        except ValueError:
            continue  # points outside the bundle; not an internal edge

    return Document(
        path=rel,
        concept_id=concept.concept_id,
        doc_type=concept.type,
        title=concept.title,
        status=concept.status,
        headings=extract_headings(concept.body),
        # De-duplicate while preserving first-seen order, so the model is stable.
        links_out=tuple(dict.fromkeys(links)),
        fields=routing_fields(concept.frontmatter),
    )


def extract_documents(bundle: Bundle, root: Path) -> list[Document]:
    """Every concept in a bundle, as `Document`s, ordered by path."""
    documents = [
        concept_document(concept, bundle, root) for _, concept in sorted(bundle.concepts().items())
    ]
    return sorted(documents, key=lambda d: d.path)


def extract_registry_tables(root: Path, rel_paths: list[str]) -> list[RegistryTable]:
    """Registry tables from the named files, ordered by path.

    `rel_paths` is supplied by configuration, so the harness never guesses which
    documents are registries.
    """
    resolved_root = root.resolve()
    tables: list[RegistryTable] = []
    for rel in sorted(rel_paths):
        path = resolved_root / rel
        if not path.is_file():
            continue
        for columns, rows in parse_markdown_tables(path.read_text(encoding="utf-8")):
            tables.append(RegistryTable(source=rel, columns=columns, rows=rows))
    return tables
