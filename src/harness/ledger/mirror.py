"""An optional Postgres mirror of the session ledger, derived from the notes.

`HARNESS_ARCHITECTURE.md` §9 names step 5 as "`git notes` + Postgres". The same
reasoning as step 1 applies (§5): git is the source of truth and the database is a
derived, rebuildable index. So the mirror is written **from the notes and nothing
else**, and its identity is proved the same way — drop it, rebuild from the notes,
compare.

The mirror exists for the joins §5.2 says git cannot do: "which sessions touched a
work item?" is a query, not a log read. It is optional: a repository with no
database still has a complete ledger, because the notes are the record.

Each row stores **both** the queryable columns (so SQL can join) and the whole
record as canonical JSON. Storing only the columns would mean the mirror could
never be proved identical to its source — the invariant would be unprovable by
construction, which is worse than not having it.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from harness.ledger.notes import DEFAULT_NOTES_REF, read_all
from harness.ledger.record import SessionRecord, parse_record

if TYPE_CHECKING:
    from pathlib import Path

    from psycopg import Connection

#: Bumped with the DDL below.
LEDGER_SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS ledger_meta (
    id              integer PRIMARY KEY CHECK (id = 1),
    schema_version  integer NOT NULL,
    record_version  integer NOT NULL,
    notes_ref       text    NOT NULL,
    digest          text    NOT NULL,
    record_count    integer NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  text PRIMARY KEY,
    work_id     text NOT NULL,
    commit_sha  text NOT NULL,
    at          text NOT NULL,
    prompt_fingerprint text,
    prompt_budget      integer,
    prompt_unit        text,
    prompt_entry_count integer,
    verdict_summary    text,
    verdict_may_execute boolean,
    effect_state       text,
    effect_detail      text,
    digest             text NOT NULL,
    record_json        text NOT NULL
);
"""

#: Created separately so the table DDL stays readable. Idempotent, because the
#: table itself is not re-created when it already exists.
INDEXES = """
CREATE INDEX IF NOT EXISTS sessions_work_id_idx ON sessions (work_id);
CREATE INDEX IF NOT EXISTS sessions_commit_idx ON sessions (commit_sha);
CREATE INDEX IF NOT EXISTS sessions_effect_idx ON sessions (effect_state);
CREATE INDEX IF NOT EXISTS sessions_fingerprint_idx ON sessions (prompt_fingerprint);
"""

DROP = """
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS ledger_meta;
"""


def canonical(records: list[SessionRecord]) -> str:
    """A stable digest over every record, in one canonical form.

    Used for *both* sides of the invariant — the notes as read from git, and the
    rows as read back from the database — so "identical" means the same thing to
    each.
    """
    payload = json.dumps([r.as_dict() for r in records], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ledger_digest(root: Path, *, ref: str = DEFAULT_NOTES_REF) -> str:
    """The digest of the ledger as read from the notes. The source side."""
    return canonical(read_all(root, ref=ref))


def reset(conn: Connection[Any]) -> None:
    """Drop and recreate the mirror tables. The "destroy" half of the proof."""
    with conn.cursor() as cur:
        cur.execute(DROP)
        cur.execute(DDL)
        cur.execute(INDEXES)
    conn.commit()


def write_mirror(root: Path, conn: Connection[Any], *, ref: str = DEFAULT_NOTES_REF) -> int:
    """Write the ledger into Postgres, from the notes alone. Returns the count.

    Resets first, so the mirror is a rendering of the *current* ledger rather than
    an accumulation of past ones. An entry removed from the notes disappears from
    the mirror too — otherwise the mirror would slowly become authoritative, which
    is the drift §5 exists to prevent.
    """
    records = read_all(root, ref=ref)
    reset(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ledger_meta (id, schema_version, record_version, notes_ref, "
            "digest, record_count) VALUES (1, %s, %s, %s, %s, %s)",
            (LEDGER_SCHEMA_VERSION, 1, ref, canonical(records), len(records)),
        )
        for record in records:
            verdict = record.verdict or {}
            cur.execute(
                """
                INSERT INTO sessions (session_id, work_id, commit_sha, at,
                    prompt_fingerprint, prompt_budget, prompt_unit, prompt_entry_count,
                    verdict_summary, verdict_may_execute, effect_state, effect_detail,
                    digest, record_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.session_id,
                    record.work_id,
                    record.commit_sha,
                    record.at,
                    record.prompt.fingerprint if record.prompt else None,
                    record.prompt.budget if record.prompt else None,
                    record.prompt.unit if record.prompt else None,
                    record.prompt.entry_count if record.prompt else None,
                    str(verdict.get("summary", "")) or None,
                    verdict.get("may_execute"),
                    record.effect.state,
                    record.effect.detail,
                    record.digest,
                    record.to_line(),
                ),
            )
    conn.commit()
    return len(records)


def read_back(conn: Connection[Any]) -> list[SessionRecord]:
    """Reconstruct the records from the rows, touching no files and no git.

    Reading only from the database is what makes the mirror invariant a real test:
    a fact that failed to round-trip changes the digest.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT record_json FROM sessions ORDER BY commit_sha, at, session_id")
        rows = cur.fetchall()
    return [parse_record(row[0]) for row in rows]


def mirror_digest(conn: Connection[Any]) -> str:
    """The digest of what the mirror holds, in the same canonical form as the notes."""
    return canonical(read_back(conn))


def sessions_for_work_item(conn: Connection[Any], work_id: str) -> list[dict[str, Any]]:
    """Every session that touched a work item — the join that is not a log read.

    This is why the mirror exists: `git log` cannot answer it without reading every
    note, and §5.2 says asking it of git is asking the wrong tool.
    """
    columns = (
        "session_id",
        "commit_sha",
        "at",
        "prompt_fingerprint",
        "verdict_summary",
        "verdict_may_execute",
        "effect_state",
    )
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(columns)} FROM sessions WHERE work_id = %s ORDER BY at",  # noqa: S608
            (work_id,),
        )
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
