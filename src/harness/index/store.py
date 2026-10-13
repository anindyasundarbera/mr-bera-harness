"""The derived PostgreSQL index: write a model, read it back.

Two properties are load-bearing and both are exercised by tests:

* **Derived, not authored.** The only writer is `write_model`, and it writes an
  `IndexModel` that came from git. Nothing here invents a value. The index can be
  dropped at any time (`reset`) and rebuilt from git.
* **Rebuildable.** `read_model` reconstructs an `IndexModel` from the rows alone.
  The rebuild invariant is then a digest comparison, and it is meaningful
  precisely because `read_model` never touches the filesystem or git: if the rows
  lost a fact, the digest changes.

`psycopg` is an optional extra. Importing this module without it is fine; calling
`connect` is not.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from harness.extract.model import MODEL_VERSION, Document, IndexModel, RegistryTable, model_digest

if TYPE_CHECKING:
    from psycopg import Connection


class IndexUnavailableError(Exception):
    """Raised when PostgreSQL cannot be reached, with the DSN redacted."""


def _redact(dsn: str) -> str:
    """Remove credentials before a DSN reaches a message or a log."""
    scheme, sep, rest = dsn.partition("://")
    if not sep or "@" not in rest:
        return dsn
    return f"{scheme}://***@{rest.rsplit('@', 1)[-1]}"


def connect(dsn: str | None) -> Connection[Any]:
    """Open a connection, or raise `IndexUnavailableError` with a redacted DSN.

    Deliberately no default DSN: the harness must not guess a database location
    any more than it guesses a document path.
    """
    if not dsn:
        raise IndexUnavailableError(
            "no PostgreSQL DSN provided (set MRB_HARNESS_DSN or pass --dsn)"
        )
    try:
        import psycopg  # noqa: PLC0415 - optional extra, imported only when used
    except ImportError as exc:  # pragma: no cover - depends on the install extras
        raise IndexUnavailableError(
            "psycopg is not installed; install the extra with `pip install -e '.[postgres]'`"
        ) from exc

    try:
        return psycopg.connect(dsn)
    except Exception as exc:  # noqa: BLE001 - any driver error means "unavailable"
        raise IndexUnavailableError(f"cannot connect to {_redact(dsn)}: {exc}") from exc


def reset(conn: Connection[Any]) -> None:
    """Drop and recreate the index tables. This is the "destroy" half of the proof."""
    from harness.index.schema import DDL, DROP  # noqa: PLC0415 - avoids a cycle at import

    with conn.cursor() as cur:
        cur.execute(DROP)
        cur.execute(DDL)
    conn.commit()


def write_model(conn: Connection[Any], model: IndexModel) -> str:
    """Write a model to the index. Returns the model digest that was written."""
    from harness.index.schema import INDEX_SCHEMA_VERSION  # noqa: PLC0415

    digest = model_digest(model)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_meta
              (id, project, commit_sha, source_rev, model_version, schema_version,
               digest, document_count, table_count)
            VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
              project = EXCLUDED.project,
              commit_sha = EXCLUDED.commit_sha,
              source_rev = EXCLUDED.source_rev,
              model_version = EXCLUDED.model_version,
              schema_version = EXCLUDED.schema_version,
              digest = EXCLUDED.digest,
              document_count = EXCLUDED.document_count,
              table_count = EXCLUDED.table_count
            """,
            (
                model.project,
                model.commit_sha,
                model.source_rev,
                model.model_version,
                INDEX_SCHEMA_VERSION,
                digest,
                len(model.documents),
                len(model.registry_tables),
            ),
        )

        for doc in sorted(model.documents, key=lambda d: d.path):
            cur.execute(
                """
                INSERT INTO documents (path, concept_id, doc_type, title, status, headings)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (doc.path, doc.concept_id, doc.doc_type, doc.title, doc.status, list(doc.headings)),
            )
            for key in sorted(doc.fields):
                cur.execute(
                    "INSERT INTO document_fields (path, key, value) VALUES (%s, %s, %s)",
                    (doc.path, key, _field_text(doc.fields[key])),
                )
            for ordinal, dst in enumerate(doc.links_out):
                cur.execute(
                    "INSERT INTO document_links (src, dst, ordinal) VALUES (%s, %s, %s)",
                    (doc.path, dst, ordinal),
                )

        for source, tables in _group_tables(model).items():
            for ordinal, table in enumerate(tables):
                cur.execute(
                    "INSERT INTO registry_tables (source, ordinal, columns) VALUES (%s, %s, %s)",
                    (source, ordinal, list(table.columns)),
                )
                for row_index, row in enumerate(table.rows):
                    cur.execute(
                        "INSERT INTO registry_rows (source, ordinal, row_index) "
                        "VALUES (%s, %s, %s)",
                        (source, ordinal, row_index),
                    )
                    for key in sorted(row):
                        cur.execute(
                            """
                            INSERT INTO registry_cells (source, ordinal, row_index, key, value)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (source, ordinal, row_index, key, row[key]),
                        )
    conn.commit()
    return digest


def read_model(conn: Connection[Any]) -> IndexModel:
    """Reconstruct a model from the rows, touching no files and no git.

    Reading only from the database is what makes the rebuild invariant a real
    test: if any fact failed to round-trip, the reconstructed digest differs.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT project, commit_sha, source_rev, model_version FROM index_meta WHERE id = 1"
        )
        meta = cur.fetchone()
        if meta is None:
            return IndexModel(project="", commit_sha="", source_rev="", model_version=MODEL_VERSION)
        project, commit_sha, source_rev, model_version = meta

        # Each query is fetched fully before the next runs: one cursor cannot
        # hold two open result sets, and interleaving them returned stale rows.
        cur.execute("SELECT path, concept_id, doc_type, title, status, headings FROM documents")
        document_rows = cur.fetchall()
        fields = _load_fields(cur)
        links = _load_links(cur)
        tables = _load_tables(cur)

    documents = tuple(
        Document(
            path=path,
            concept_id=concept_id,
            doc_type=doc_type,
            title=title,
            status=status,
            headings=tuple(headings or ()),
            links_out=tuple(links.get(path, ())),
            fields=fields.get(path, {}),
        )
        for path, concept_id, doc_type, title, status, headings in document_rows
    )

    return IndexModel(
        project=project,
        commit_sha=commit_sha,
        source_rev=source_rev,
        model_version=int(model_version),
        documents=documents,
        registry_tables=tables,
    )


def _field_text(value: object) -> str:
    """Serialize a field value the same way both when writing and reading."""
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _load_fields(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute("SELECT path, key, value FROM document_fields")
    rows = cur.fetchall()
    result: dict[str, dict[str, Any]] = {}
    for path, key, value in rows:
        if value[:1] == "[":
            try:
                result.setdefault(path, {})[key] = json.loads(value)
                continue
            except ValueError:
                pass
        result.setdefault(path, {})[key] = value
    return result


def _load_links(cur: Any) -> dict[str, list[str]]:
    cur.execute("SELECT src, dst FROM document_links ORDER BY src, ordinal")
    rows = cur.fetchall()
    result: dict[str, list[str]] = {}
    for src, dst in rows:
        result.setdefault(src, []).append(dst)
    return result


def _load_tables(cur: Any) -> tuple[RegistryTable, ...]:
    cur.execute("SELECT source, ordinal, columns FROM registry_tables ORDER BY source, ordinal")
    table_rows = cur.fetchall()
    # Row identity is read from `registry_rows`, not inferred from the cells, so a
    # row whose every cell is empty still round-trips.
    cur.execute(
        "SELECT source, ordinal, row_index FROM registry_rows ORDER BY source, ordinal, row_index"
    )
    row_rows = cur.fetchall()
    cur.execute(
        "SELECT source, ordinal, row_index, key, value FROM registry_cells "
        "ORDER BY source, ordinal, row_index, key"
    )
    cell_rows = cur.fetchall()

    cells: dict[tuple[str, int], dict[int, dict[str, str]]] = {}
    for source, ordinal, row_index, key, value in cell_rows:
        cells.setdefault((source, ordinal), {}).setdefault(row_index, {})[key] = value
    indices: dict[tuple[str, int], list[int]] = {}
    for source, ordinal, row_index in row_rows:
        indices.setdefault((source, ordinal), []).append(row_index)

    tables: list[RegistryTable] = []
    for source, ordinal, columns in table_rows:
        key = (source, ordinal)
        cells_for_table = cells.get(key, {})
        tables.append(
            RegistryTable(
                source=source,
                columns=tuple(columns),
                rows=tuple(cells_for_table.get(i, {}) for i in indices.get(key, [])),
            )
        )
    return tuple(tables)


def _group_tables(model: IndexModel) -> dict[str, list[RegistryTable]]:
    grouped: dict[str, list[RegistryTable]] = {}
    for table in sorted(model.registry_tables, key=lambda t: t.source):
        grouped.setdefault(table.source, []).append(table)
    return grouped
