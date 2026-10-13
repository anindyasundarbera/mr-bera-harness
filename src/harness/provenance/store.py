"""The provenance links, in the optional index, so they can be joined.

The owner's requirement was that the links live **in the database as well as in the
codebase**, with the decision's hash connecting the files. Two things follow:

* The same hash appears in the source declaration and in the row, so a query can find
  every file whose declared hash no longer matches its decision — the join that makes
  a stale link visible across a whole repository rather than one file at a time.
* Like every other store here, this is **derived** (`§5`). It is written from the
  declarations and the decision records, and it is rebuildable. A link is authored in
  the source file, never here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from harness.provenance.links import DIGEST_PREFIX_LENGTH, Decision, Declaration

if TYPE_CHECKING:
    from psycopg import Connection

    from harness.config import Config

#: Bumped with the DDL below.
PROVENANCE_SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id    text PRIMARY KEY,
    path           text NOT NULL,
    title          text NOT NULL,
    status         text NOT NULL,
    anchor_digest  text NOT NULL
);

CREATE TABLE IF NOT EXISTS code_links (
    path           text NOT NULL,
    line           integer NOT NULL,
    decision_id    text NOT NULL,
    declared_digest text NOT NULL,
    matches        boolean NOT NULL,
    PRIMARY KEY (path, line, decision_id)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS code_links_decision_idx ON code_links (decision_id);
CREATE INDEX IF NOT EXISTS code_links_stale_idx ON code_links (matches) WHERE NOT matches;
"""

DROP = """
DROP TABLE IF EXISTS code_links;
DROP TABLE IF EXISTS decisions;
"""


def reset(conn: Connection[Any]) -> None:
    """Drop and recreate. The "destroy" half of the rebuild proof."""
    with conn.cursor() as cur:
        cur.execute(DROP)
        cur.execute(DDL)
        cur.execute(INDEXES)
    conn.commit()


def write_links(conn: Connection[Any], config: Config, *, require_all: bool = False) -> int:
    """Write every declaration and decision into the index. Returns the row count.

    Derived and rebuilt on each call, like every other store here: the rows are a
    rendering of what the source declares, never an authority. A declaration removed
    from a file disappears from the index.
    """
    from harness.provenance.checks import check  # noqa: PLC0415 - avoids a cycle

    report = check(config, require_every_file_linked=require_all)
    reset(conn)

    with conn.cursor() as cur:
        for decision in report.decisions.values():
            cur.execute(
                "INSERT INTO decisions (decision_id, path, title, status, anchor_digest) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    decision.decision_id,
                    decision.path,
                    decision.title,
                    decision.status,
                    decision.anchor_digest,
                ),
            )
        for declaration in report.declarations:
            expected = report.decisions.get(declaration.decision_id)
            matches = bool(
                expected and declaration.digest == expected.anchor_digest[:DIGEST_PREFIX_LENGTH]
            )
            cur.execute(
                "INSERT INTO code_links (path, line, decision_id, declared_digest, matches) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    declaration.path,
                    declaration.line,
                    declaration.decision_id,
                    declaration.digest,
                    matches,
                ),
            )
    conn.commit()
    return len(report.declarations)


def stale_links(conn: Connection[Any]) -> list[dict[str, Any]]:
    """Every link whose declared hash no longer matches its decision.

    This is the query the hash exists to make possible: *which code was written
    against a decision that has since changed?* It is a join across the whole
    repository, which is why it belongs in SQL rather than in a file-by-file check.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT l.path, l.line, l.decision_id, l.declared_digest, d.anchor_digest
            FROM code_links l LEFT JOIN decisions d ON d.decision_id = l.decision_id
            WHERE NOT l.matches
            ORDER BY l.path, l.line
            """
        )
        columns = ("path", "line", "decision_id", "declared_digest", "anchor_digest")
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def files_for_decision(conn: Connection[Any], decision_id: str) -> list[dict[str, Any]]:
    """Which files declare a decision — the reverse index a reader wants."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT path, line, declared_digest, matches FROM code_links "
            "WHERE decision_id = %s ORDER BY path, line",
            (decision_id,),
        )
        columns = ("path", "line", "declared_digest", "matches")
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def decisions_without_code(conn: Connection[Any]) -> list[str]:
    """Decisions no file declares.

    Reported, not treated as an error: a decision can be about process, or about a
    document, and not every decision produces code.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT d.decision_id FROM decisions d "
            "LEFT JOIN code_links l ON l.decision_id = d.decision_id "
            "WHERE l.decision_id IS NULL ORDER BY d.decision_id"
        )
        return [row[0] for row in cur.fetchall()]


def read_links(conn: Connection[Any]) -> tuple[dict[str, Decision], list[Declaration]]:
    """Reconstruct the model from the rows, touching no files and no git.

    Reading only from the database is what makes the rebuild comparison real.
    """
    decisions: dict[str, Decision] = {}
    declarations: list[Declaration] = []
    with conn.cursor() as cur:
        cur.execute("SELECT decision_id, path, title, status, anchor_digest FROM decisions")
        for decision_id, path, title, status, digest in cur.fetchall():
            decisions[decision_id] = Decision(decision_id, path, title, status, digest)
        cur.execute("SELECT path, line, decision_id, declared_digest FROM code_links")
        for path, line, decision_id, digest in cur.fetchall():
            declarations.append(
                Declaration(path=path, line=line, decision_id=decision_id, digest=digest)
            )
    return decisions, declarations
