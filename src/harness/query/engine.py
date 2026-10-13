"""Query the derived index with SQL, so a lookup costs no tokens.

This is build-order step 2 of `HARNESS_ARCHITECTURE.md` §9: *the lookup surface
that replaces file-reading*. Most agent questions are lookups wearing a costume —
"which documents bind task Y?", "is this blocked?", "what depends on this?" — and
each one moved from "a model answers" to "code answers" removes both tokens and a
hallucination surface.

The engine is deliberately a thin layer over SQL rather than a second model of the
data. It reads the derived index (`harness.index`), never the working tree, so a
query result is a function of a committed revision.

`touching` and `blocked` mirror semantics the routing layer already enforces in
Python (`harness.routing.resolve`). That is on purpose: the same question answered
two ways can be compared, and a test does exactly that. Where they could disagree,
the Python resolver is the reference — it is what an agent actually runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from psycopg import Connection

#: The concept type that carries a stop condition rather than content. Mirrors
#: `harness.routing.resolve.STOP_CONCEPT_TYPE` so the two cannot drift silently;
#: a test asserts they agree.
STOP_CONCEPT_TYPE = "Unknown"

#: The list-valued routing fields a scope query may intersect. A query for the
#: literal value `MRB-M06` matches only documents that name `MRB-M06`, never
#: `MRB-M06-S07` — an element match, not a substring match.
SCOPE_FIELDS = ("covers", "depends_on", "blocks", "do_not_use_for", "tags", "module")

_DOCUMENT_COLUMNS = "path, concept_id, doc_type, title, status, headings"
_DOCUMENT_COLUMNS_QUALIFIED = "d.path, d.concept_id, d.doc_type, d.title, d.status, d.headings"


@dataclass(frozen=True)
class Row:
    """One document as the index holds it."""

    path: str
    concept_id: str
    doc_type: str
    title: str
    status: str
    headings: tuple[str, ...] = ()
    fields: dict[str, Any] = field(default_factory=dict)
    links_out: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "concept_id": self.concept_id,
            "doc_type": self.doc_type,
            "title": self.title,
            "status": self.status,
            "headings": list(self.headings),
            "fields": self.fields,
            "links_out": list(self.links_out),
        }


@dataclass(frozen=True)
class Blocked:
    """A stop condition: an `Unknown` whose scope covers the work item."""

    concept_id: str
    path: str
    title: str
    state: str
    blocker: str
    blocks: tuple[str, ...]
    if_you_guess: str = ""
    must_not_do: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "path": self.path,
            "title": self.title,
            "state": self.state,
            "blocker": self.blocker,
            "blocks": list(self.blocks),
            "if_you_guess": self.if_you_guess,
            "must_not_do": list(self.must_not_do),
        }


def _decode(value: str) -> Any:
    """Decode a stored field value back into a str or list."""
    if value[:1] == "[":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _field_map(cur: Any, paths: list[str]) -> dict[str, dict[str, Any]]:
    """Load `fields` for the given documents in one query."""
    if not paths:
        return {}
    cur.execute("SELECT path, key, value FROM document_fields WHERE path = ANY(%s)", (paths,))
    result: dict[str, dict[str, Any]] = {}
    for path, key, value in cur.fetchall():
        result.setdefault(path, {})[key] = _decode(value)
    return result


def _link_map(cur: Any, paths: list[str]) -> dict[str, list[str]]:
    if not paths:
        return {}
    cur.execute(
        "SELECT src, dst FROM document_links WHERE src = ANY(%s) ORDER BY src, ordinal",
        (paths,),
    )
    result: dict[str, list[str]] = {}
    for src, dst in cur.fetchall():
        result.setdefault(src, []).append(dst)
    return result


def _rows_from(cur: Any, records: list[tuple[Any, ...]]) -> list[Row]:
    paths = [r[0] for r in records]
    fields = _field_map(cur, paths)
    links = _link_map(cur, paths)
    return [
        Row(
            path=path,
            concept_id=concept_id,
            doc_type=doc_type,
            title=title,
            status=status,
            headings=tuple(headings or ()),
            fields=fields.get(path, {}),
            links_out=tuple(links.get(path, ())),
        )
        for path, concept_id, doc_type, title, status, headings in records
    ]


def documents(
    conn: Connection[Any],
    *,
    doc_type: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> list[Row]:
    """Documents, optionally filtered by type or status."""
    sql = f"SELECT {_DOCUMENT_COLUMNS} FROM documents"  # noqa: S608 - fixed column list
    clauses: list[str] = []
    params: list[Any] = []
    if doc_type:
        clauses.append("doc_type = %s")
        params.append(doc_type)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY path"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return _rows_from(cur, cur.fetchall())


def show(conn: Connection[Any], concept_id: str) -> Row | None:
    """One document by concept id or by path, with its links resolved."""
    key = concept_id.strip().removeprefix("./")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM documents "  # noqa: S608 - fixed columns
            "WHERE concept_id = %s OR path = %s OR path = %s ORDER BY path LIMIT 1",
            (key, key, f"{key}.md"),
        )
        records = cur.fetchall()
        return _rows_from(cur, records)[0] if records else None


def search(conn: Connection[Any], text: str, limit: int = 50) -> list[Row]:
    """Case-insensitive substring match over title, concept id and headings.

    A lookup, not a semantic search. Its job is to replace an agent reading files
    to find which document mentions something.
    """
    pattern = f"%{text}%"
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_DOCUMENT_COLUMNS} FROM documents "  # noqa: S608 - fixed columns
            "WHERE title ILIKE %s OR concept_id ILIKE %s "
            "OR EXISTS (SELECT 1 FROM unnest(headings) AS h WHERE h ILIKE %s) "
            "ORDER BY path LIMIT %s",
            (pattern, pattern, pattern, limit),
        )
        return _rows_from(cur, cur.fetchall())


def links(conn: Connection[Any], concept_id: str, *, direction: str = "out") -> list[str]:
    """Concept ids linked from (or to) a document.

    The link graph is what turns "what does this depend on?" into a query.
    """
    if direction not in {"in", "out"}:
        raise ValueError(f"direction must be 'in' or 'out', not {direction!r}")
    key = concept_id.strip().removeprefix("./")
    with conn.cursor() as cur:
        if direction == "out":
            cur.execute(
                "SELECT d.dst FROM document_links d JOIN documents s ON s.path = d.src "
                "WHERE s.concept_id = %s OR s.path = %s OR s.path = %s ORDER BY d.ordinal",
                (key, key, f"{key}.md"),
            )
        else:
            cur.execute(
                "SELECT s.concept_id FROM document_links d JOIN documents s ON s.path = d.src "
                "WHERE d.dst = %s ORDER BY s.concept_id",
                (key,),
            )
        return [row[0] for row in cur.fetchall()]


def touching(conn: Connection[Any], work_id: str, *, field_name: str = "covers") -> list[Row]:
    """Documents whose `field_name` names `work_id` exactly.

    An element match: `MRB-M06` does not select a document that covers only
    `MRB-M06-S07`. This is the join §5.2 says belongs in SQL.
    """
    if field_name not in SCOPE_FIELDS:
        raise ValueError(f"field must be one of {', '.join(SCOPE_FIELDS)}, not {field_name!r}")
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_DOCUMENT_COLUMNS_QUALIFIED} "  # noqa: S608 - fixed column list
            "FROM documents d JOIN document_field_items i ON i.path = d.path "
            "WHERE i.key = %s AND i.item = %s ORDER BY d.path",
            (field_name, work_id.strip()),
        )
        return _rows_from(cur, cur.fetchall())


def blocked(conn: Connection[Any], work_id: str) -> list[Blocked]:
    """Stop conditions that apply to a work item.

    A stop condition is an `Unknown` concept whose `blocks` names the work item.
    This is the SQL form of what `harness context` reports as exit code 3, and the
    wording is kept close to the resolver's so a reader sees the same thing in
    both places.
    """
    key = work_id.strip()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.path, d.concept_id, d.title FROM documents d "
            "JOIN document_field_items i ON i.path = d.path "
            "WHERE d.doc_type = %s AND i.key = 'blocks' AND i.item = %s "
            "ORDER BY d.concept_id",
            (STOP_CONCEPT_TYPE, key),
        )
        records = cur.fetchall()
        fields = _field_map(cur, [r[0] for r in records])

    result: list[Blocked] = []
    for path, concept_id, title in records:
        meta = fields.get(path, {})
        blocks = meta.get("blocks", [])
        result.append(
            Blocked(
                concept_id=concept_id,
                path=path,
                title=title,
                state=str(meta.get("state", "")),
                blocker=str(meta.get("blocker", "")),
                blocks=tuple(blocks if isinstance(blocks, list) else [blocks]),
                if_you_guess=str(meta.get("if_you_guess") or ""),
                must_not_do=tuple(meta.get("must_not_do") or []),
            )
        )
    return result


def stops(conn: Connection[Any], *, state: str | None = None) -> list[dict[str, Any]]:
    """Every stop condition, with the work items it blocks — one row per pair.

    This is the join `HARNESS_ARCHITECTURE.md` §5.2 names as belonging in SQL:
    "which work items are blocked, and by which stop condition". Answering it from
    files means reading every `Unknown` concept and correlating by hand; here it
    is one query over the element-wise index.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.item AS blocked_item, bl.item AS blocker, st.item AS state, d.title
            FROM document_field_items b
            JOIN documents d             ON d.path = b.path
            JOIN document_field_items bl ON bl.path = b.path AND bl.key = 'blocker'
            JOIN document_field_items st ON st.path = b.path AND st.key = 'state'
            WHERE b.key = 'blocks' AND d.doc_type = %s
            ORDER BY blocked_item, blocker
            """,
            (STOP_CONCEPT_TYPE,),
        )
        rows = cur.fetchall()
    return [
        {"work_item": work_item, "blocker": blocker, "state": row_state, "title": title}
        for work_item, blocker, row_state, title in rows
        if state is None or row_state == state
    ]


def decisions(conn: Connection[Any], *, status: str | None = None) -> list[Row]:
    """Decision records held in the index, optionally filtered by status."""
    return documents(conn, doc_type="Decision Record", status=status)


def gaps(conn: Connection[Any], *, state: str | None = None) -> list[dict[str, str]]:
    """Rows from a gap register, as stored by the registry extractor.

    Registry tables carry a state column whose *name* comes from configuration,
    so the state is matched by column name, never by position.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source, row_index, key, value FROM registry_cells "
            "ORDER BY source, ordinal, row_index, key"
        )
        rows: dict[tuple[str, int], dict[str, str]] = {}
        for source, row_index, key, value in cur.fetchall():
            rows.setdefault((source, row_index), {})[key] = value

    result: list[dict[str, str]] = []
    for (source, _index), cells in sorted(rows.items()):
        if state is not None and not _matches_state(cells, state):
            continue
        result.append({"source": source, **cells})
    return result


def _matches_state(cells: dict[str, str], state: str) -> bool:
    """True when a cell named like a state column holds `state`."""
    return any(value == state and "state" in key.lower() for key, value in cells.items())
