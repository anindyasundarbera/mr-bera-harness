"""Append-only session records in `git notes`.

`HARNESS_ARCHITECTURE.md` §5.3 gives git the role of durable memory and `git notes`
the role of metadata that does not rewrite history:

> Git is already an append-only, content-addressed, cryptographically ordered event
> log with a distributed transport. The design does not add a store; it **reads the
> one already present.**

So a session record lives in a note attached to the commit it concerns. The note
survives a repository copy, which is the property §10 lists as the reason to prefer
it over Postgres alone.

**A transport limitation, measured rather than assumed.** A `git notes` ref is not
fetched by a plain `git clone` or `git fetch`. The records travel only when the ref
is pushed and fetched explicitly:

    git push origin refs/notes/<ref>
    git fetch origin refs/notes/<ref>:refs/notes/<ref>

`harness ledger push-ref` prints the exact commands. A ledger that appeared to work
locally and silently did not travel would be worse than no ledger, so this is
documented in the design note and exposed by the CLI rather than left implicit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness.ledger.record import (
    RecordError,
    SessionRecord,
    parse_record,
)

#: The default notes ref. Namespaced so it cannot collide with a project's own
#: notes, and configurable so a consumer may choose another.
DEFAULT_NOTES_REF = "harness"


class NotesError(Exception):
    """Raised when a notes operation fails."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def _ref(ref: str) -> str:
    return f"refs/notes/{ref}"


def has_note(root: Path, commit_sha: str, *, ref: str = DEFAULT_NOTES_REF) -> bool:
    return _git(root, "notes", f"--ref={ref}", "show", commit_sha).returncode == 0


def append_record(root: Path, record: SessionRecord, *, ref: str = DEFAULT_NOTES_REF) -> None:
    """Append one record to the note on `record.commit_sha`.

    `git notes append` creates the note when none exists, so append-only is uniform
    whether this is the first record on a commit or the tenth. The ref option must
    precede the subcommand — `git notes append --ref=x` is rejected — which is why
    the argument order here is not the obvious one.
    """
    proc = _git(root, "notes", f"--ref={ref}", "append", "-m", record.to_line(), record.commit_sha)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown git error"
        raise NotesError(f"could not append a record to {record.commit_sha[:12]}: {detail}")


def read_note(root: Path, commit_sha: str, *, ref: str = DEFAULT_NOTES_REF) -> list[SessionRecord]:
    """Every record attached to a commit, in the order they were appended."""
    proc = _git(root, "notes", f"--ref={ref}", "show", commit_sha)
    if proc.returncode != 0:
        return []  # no note on this commit is not an error; it is an empty ledger
    return parse_note(proc.stdout)


def parse_note(text: str) -> list[SessionRecord]:
    """Parse a note body into records.

    `git notes append` separates messages with a blank line, and a record is always
    one line, so the split is unambiguous. A non-blank separator would make the
    boundary depend on content.
    """
    records: list[SessionRecord] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(parse_record(stripped))
    return records


def read_all(root: Path, *, ref: str = DEFAULT_NOTES_REF) -> list[SessionRecord]:
    """Every record in the ledger, oldest commit first.

    `git log --notes` walks history and prints note bodies, so this reads the whole
    ledger in one command rather than one process per commit.
    """
    if not _git(root, "rev-parse", "--verify", "--quiet", _ref(ref)).stdout.strip():
        return []

    proc = _git(root, "log", "--format=%H%n%N%x00", f"--notes={ref}", "--reverse")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "unknown git error"
        raise NotesError(f"could not read the ledger: {detail}")

    records: list[SessionRecord] = []
    for block in proc.stdout.split("\x00"):
        text = block.strip()
        if not text:
            continue
        # Each block is "<sha>\n<note body>"; the sha is not needed to parse.
        _, _, body = text.partition("\n")
        try:
            records.extend(parse_note(body))
        except RecordError as exc:
            raise NotesError(f"a stored record is unreadable: {exc}") from exc
    return records


def record_count(root: Path, *, ref: str = DEFAULT_NOTES_REF) -> int:
    return len(read_all(root, ref=ref))


def push_commands(ref: str = DEFAULT_NOTES_REF) -> tuple[str, str]:
    """The exact commands that transport the ledger.

    Returned rather than executed: pushing is a separate, authorised action, and a
    library that pushed on its own would be a network side effect nobody asked for.
    """
    return (
        f"git push origin {_ref(ref)}",
        f"git fetch origin {_ref(ref)}:{_ref(ref)}",
    )


def notes_exist(root: Path, *, ref: str = DEFAULT_NOTES_REF) -> bool:
    """Whether the ledger ref exists locally at all."""
    return bool(_git(root, "rev-parse", "--verify", "--quiet", _ref(ref)).stdout.strip())
