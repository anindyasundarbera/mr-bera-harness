"""One session-record entry: what was proposed, decided and observed.

Build-order step 5 of `HARNESS_ARCHITECTURE.md` §9 records "prompt, proposal,
verdict, effect". This module is that entry.

Three deliberate choices:

* **The prompt is recorded by fingerprint, not by text.** Step 3's fingerprint
  covers the prompt bytes *and* the manifest of what is in it, so a recorded
  fingerprint proves what was sent without storing it twice. A ledger that
  duplicated the prompt would be a second copy to keep in step.
* **The record states what it does not know.** `effect` is the caller's report of
  what happened; the ledger does **not** execute, so it cannot observe an effect
  itself. An `effect` of `not-observed` is honest; an invented one is not.
* **The record is versioned**, like `PROPOSAL_SCHEMA_VERSION` and `MODEL_VERSION`.
  A change to this shape invalidates a recorded entry, and an entry that does not
  state its version cannot be read correctly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: Bumped whenever the record shape changes.
RECORD_VERSION = 1

#: What is known about the effect of a permitted proposal.
#:
#: The ledger records; it does not execute. So an effect is either reported by the
#: caller (`applied`, `failed`) or explicitly not observed. `not-observed` is the
#: default and is not a failure — it is the truth about a recorder.
EFFECT_NOT_OBSERVED = "not-observed"
EFFECT_APPLIED = "applied"
EFFECT_FAILED = "failed"
EFFECT_NONE = "none"

EFFECTS = (EFFECT_NOT_OBSERVED, EFFECT_APPLIED, EFFECT_FAILED, EFFECT_NONE)


@dataclass(frozen=True)
class PromptRef:
    """What was sent, by reference: the step-3 fingerprint and how it was bounded."""

    fingerprint: str
    budget: int
    unit: str
    entry_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Effect:
    """What the caller reports happened after the verdict.

    The ledger has no executor, so it cannot observe this. `state` defaults to
    `not-observed`, the truthful value for a recorder that was not told.
    """

    state: str = EFFECT_NOT_OBSERVED
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionRecord:
    """One ledger entry, bound to a commit.

    `commit_sha` is the commit the note is attached to. `at` is the only
    nondeterministic field, recorded as provenance rather than as a fact about the
    code — the same convention as the dashboard's `generated_at`.
    """

    session_id: str
    work_id: str
    commit_sha: str
    at: str
    prompt: PromptRef | None = None
    proposal: dict[str, Any] | None = None
    verdict: dict[str, Any] | None = None
    effect: Effect = field(default_factory=Effect)
    record_version: int = RECORD_VERSION

    def to_line(self) -> str:
        """One NDJSON line: the wire form appended to a note.

        A single line per record, because `git notes append` separates messages
        with a blank line, and a multi-line JSON document would be ambiguous to
        split back apart.
        """
        return json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_version": self.record_version,
            "session_id": self.session_id,
            "work_id": self.work_id,
            "commit_sha": self.commit_sha,
            "at": self.at,
            "prompt": self.prompt.as_dict() if self.prompt else None,
            "proposal": self.proposal,
            "verdict": self.verdict,
            "effect": self.effect.as_dict(),
        }

    @property
    def digest(self) -> str:
        """SHA-256 over the canonical record, including `at`.

        Two records that differ only in time are different records, and a digest
        that ignored that would call them equal.
        """
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RecordError(Exception):
    """Raised when a stored record cannot be read."""


def parse_record(line: str) -> SessionRecord:
    """Parse one NDJSON line back into a record, failing loudly.

    A malformed line is an error, never a skipped entry: a ledger that silently
    dropped an entry is indistinguishable from one where the event never happened.
    """
    try:
        data = json.loads(line)
    except ValueError as exc:
        raise RecordError(f"not valid JSON: {line[:60]!r}") from exc
    if not isinstance(data, dict):
        raise RecordError(f"record must be a JSON object, got {type(data).__name__}")

    version = data.get("record_version")
    if version != RECORD_VERSION:
        raise RecordError(
            f"record_version {version!r} is not {RECORD_VERSION}; a record written "
            "against another contract cannot be read as this one"
        )

    prompt_raw = data.get("prompt")
    prompt = PromptRef(**prompt_raw) if isinstance(prompt_raw, dict) else None
    effect_raw = data.get("effect")
    effect = Effect(**effect_raw) if isinstance(effect_raw, dict) else Effect()

    return SessionRecord(
        session_id=str(data.get("session_id", "")),
        work_id=str(data.get("work_id", "")),
        commit_sha=str(data.get("commit_sha", "")),
        at=str(data.get("at", "")),
        prompt=prompt,
        proposal=data.get("proposal"),
        verdict=data.get("verdict"),
        effect=effect,
        record_version=RECORD_VERSION,
    )
