"""The session ledger: what was proposed, decided and observed, bound to commits.

Build-order step 5 of `HARNESS_ARCHITECTURE.md` §9. Git is the source of truth and
`git notes` carries the record, so a session's history survives a repository copy.
The Postgres mirror is optional and derived — it exists for the joins git cannot do.

**The ledger records; it does not execute.** There is no code path here to a
mutation, which is what keeps the propose/dispose split intact across a whole
session rather than only at the moment of a proposal.
"""

from harness.ledger.mirror import (
    LEDGER_SCHEMA_VERSION,
    canonical,
    ledger_digest,
    mirror_digest,
    read_back,
    sessions_for_work_item,
    write_mirror,
)
from harness.ledger.notes import (
    DEFAULT_NOTES_REF,
    NotesError,
    append_record,
    has_note,
    notes_exist,
    push_commands,
    read_all,
    read_note,
    record_count,
)
from harness.ledger.record import (
    EFFECT_APPLIED,
    EFFECT_FAILED,
    EFFECT_NONE,
    EFFECT_NOT_OBSERVED,
    EFFECTS,
    RECORD_VERSION,
    Effect,
    PromptRef,
    RecordError,
    SessionRecord,
    parse_record,
)

__all__ = [
    "DEFAULT_NOTES_REF",
    "EFFECTS",
    "EFFECT_APPLIED",
    "EFFECT_FAILED",
    "EFFECT_NONE",
    "EFFECT_NOT_OBSERVED",
    "LEDGER_SCHEMA_VERSION",
    "RECORD_VERSION",
    "Effect",
    "NotesError",
    "PromptRef",
    "RecordError",
    "SessionRecord",
    "append_record",
    "canonical",
    "has_note",
    "ledger_digest",
    "mirror_digest",
    "write_mirror",
    "notes_exist",
    "parse_record",
    "push_commands",
    "read_all",
    "read_back",
    "read_note",
    "record_count",
    "sessions_for_work_item",
]
