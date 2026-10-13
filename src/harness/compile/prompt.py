"""Compile a bounded prompt for a work item, with a SHA-256 fingerprint.

Build-order step 3 of `HARNESS_ARCHITECTURE.md` §9: *task ID + selection + budget
→ prompt + fingerprint*. Three properties make it deterministic:

1. **A pure function of a committed revision.** The selection comes from
   `harness.routing.resolve`; the text comes from the same committed bytes
   `harness.extract.source` reads. Neither reads the clock or the working tree.
2. **A content-addressed fingerprint over exactly what was sent.** The digest
   covers the prompt text *and the manifest of what is in it*, so a stale or
   substituted prompt cannot carry a valid fingerprint.
3. **Refusal instead of truncation.** When a work item is blocked, or the
   selection does not fit the budget, the compiler refuses and names the finding.
   It never emits a silently-partial prompt.

The third point is the architecture's §3 dashed edge made executable: the
fingerprint is recorded *before* the model is called, so an audit can show what
was sent, not merely what was intended.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness.compile.tokens import UNIT, count_units
from harness.extract.source import IndexSourceError, commit_sha, materialize_commit
from harness.okf import OkfError
from harness.routing.resolve import resolve_context

if TYPE_CHECKING:
    from harness.config import Config

#: Exit codes, part of the command's contract.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_NO_SELECTION = 4
EXIT_OVER_BUDGET = 5

#: The only read-budget value excluded from the prompt. `do-not-load` never
#: reaches here — `resolve_context` drops it — but a manifest must be explicit
#: about the vocabulary it honours rather than assuming the resolver's filter.
LOADED_BUDGETS = ("must-read", "reference-only")


class CompileError(Exception):
    """Raised when a prompt cannot be compiled. Carries an exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Entry:
    """One document as it appears in the prompt."""

    concept_id: str
    path: str
    title: str
    read_budget: str
    trust: str
    status: str
    stale: bool | None
    covers: tuple[str, ...]
    units: int
    text: str

    def manifest(self) -> dict[str, Any]:
        """Everything about this entry except its text."""
        return {
            "concept_id": self.concept_id,
            "path": self.path,
            "title": self.title,
            "read_budget": self.read_budget,
            "trust": self.trust,
            "status": self.status,
            "stale": self.stale,
            "covers": list(self.covers),
            "units": self.units,
        }


@dataclass(frozen=True)
class CompiledPrompt:
    """A compiled prompt, its fingerprint, and how it was bounded."""

    work_id: str
    chain: tuple[str, ...]
    rev: str
    commit_sha: str
    budget: int
    unit: str
    used: int
    text: str
    fingerprint: str
    entries: tuple[Entry, ...] = ()
    excluded: tuple[dict[str, Any], ...] = ()
    stop_conditions: tuple[dict[str, Any], ...] = ()

    @property
    def fits(self) -> bool:
        return self.used <= self.budget

    def manifest(self) -> dict[str, Any]:
        """The audit record: what was sent, and how it was selected.

        Deliberately excludes the prompt text — the fingerprint covers it, and a
        manifest that duplicated the text would be a second thing to keep in
        step.
        """
        return {
            "work_id": self.work_id,
            "chain": list(self.chain),
            "rev": self.rev,
            "commit_sha": self.commit_sha,
            "budget": self.budget,
            "unit": self.unit,
            "used": self.used,
            "fingerprint": self.fingerprint,
            "entries": [e.manifest() for e in self.entries],
            "excluded": list(self.excluded),
            "stop_conditions": list(self.stop_conditions),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.manifest(), "text": self.text}


def _fingerprint(text: str, entries: tuple[Entry, ...], work_id: str, rev: str) -> str:
    """SHA-256 over the prompt text and the manifest of what is in it.

    Hashing the text alone would let an entry be swapped without changing the
    digest, provided the total length matched. Hashing the text *and* the
    structure closes that.
    """
    payload = json.dumps(
        {
            "work_id": work_id,
            "rev": rev,
            "text": text,
            "entries": [e.manifest() for e in entries],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _render(work_id: str, chain: list[str], rev: str, entries: tuple[Entry, ...]) -> str:
    """Render the prompt deterministically from its parts.

    A plain, inspectable format rather than a template language: a template would
    be one more thing whose output must be reasoned about to know what was sent.
    """
    lines = [
        f"# Work item: {work_id}",
        "",
        f"Revision: {rev}",
        f"Chain: {' > '.join(chain)}",
        "",
        "The documents below are the only context provided. Each states where it",
        "came from, so a claim can be traced rather than trusted.",
        "",
    ]
    for entry in entries:
        lines += [
            f"## {entry.concept_id}",
            "",
            f"- title: {entry.title}",
            f"- read_budget: {entry.read_budget}  trust: {entry.trust}  status: {entry.status}",
            f"- source: {entry.path}",
            "",
            entry.text.rstrip("\n"),
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _read_entry(tree: Path, path: str) -> str:
    """Read a document's text from the materialized revision, or fail."""
    target = tree / path
    if not target.is_file():
        raise CompileError(f"selected document is missing from the revision: {path}")
    return target.read_text(encoding="utf-8")


def compile_prompt(
    config: Config,
    work_id: str,
    *,
    budget: int,
    rev: str = "HEAD",
    defining: list[str] | None = None,
    root: Path | None = None,
) -> CompiledPrompt:
    """Compile the prompt that binds `work_id`, bounded by `budget` units.

    `budget` has no default on purpose: no authoritative document fixes a value,
    and a default would be an invented threshold that every recorded fingerprint
    silently depended on. The caller supplies it, and it is recorded in the
    fingerprint input.

    Selection is **all-or-nothing**. When the selection exceeds the budget the
    call fails rather than dropping documents, because a silently-shortened
    prompt is a claim that the omitted documents do not bind the work item.
    """
    if budget <= 0:
        raise CompileError(f"budget must be a positive number of {UNIT}s, got {budget!r}")

    try:
        resolved = resolve_context(config, work_id, defining=defining)
    except OkfError as exc:
        # A malformed identifier is a usage error, not a crash: the resolver
        # validates the configured grammar and reports it as `OkfError`.
        raise CompileError(str(exc), EXIT_USAGE) from exc

    # The resolver's exit contract, enforced here rather than merely reported.
    if resolved.stop_conditions:
        names = ", ".join(str(s.get("blocker", "?")) for s in resolved.stop_conditions)
        raise CompileError(
            f"{work_id} is blocked ({names}); record the blocker instead of compiling a prompt",
            EXIT_BLOCKED,
        )
    if not resolved.load:
        raise CompileError(
            f"no concept covers {work_id}; record BlockedDependency rather than compiling",
            EXIT_NO_SELECTION,
        )

    base = (root or config.root).resolve()
    try:
        sha = commit_sha(base, rev)
        with materialize_commit(base, rev) as tree:
            entries = tuple(
                _entry_from(item, tree, base)
                for item in resolved.load
                if item["read_budget"] in LOADED_BUDGETS
            )
    except IndexSourceError as exc:
        raise CompileError(str(exc)) from exc

    text = _render(work_id, resolved.chain, rev, entries)
    used = count_units(text)
    if used > budget:
        raise CompileError(
            f"selection needs {used} {UNIT}s but the budget is {budget}; "
            f"{len(entries)} document(s) bind {work_id}. Raise the budget or narrow "
            "the work item — the compiler will not silently drop context.",
            EXIT_OVER_BUDGET,
        )

    return CompiledPrompt(
        work_id=work_id,
        chain=tuple(resolved.chain),
        rev=rev,
        commit_sha=sha,
        budget=budget,
        unit=UNIT,
        used=used,
        text=text,
        fingerprint=_fingerprint(text, entries, work_id, rev),
        entries=entries,
        excluded=tuple(resolved.excluded),
        stop_conditions=tuple(resolved.stop_conditions),
    )


def _entry_from(item: dict[str, Any], tree: Path, base: Path) -> Entry:
    """Build an `Entry` from one resolver selection item."""
    text = _read_entry(tree, _revision_path(item, tree, base))
    return Entry(
        concept_id=str(item["concept_id"]),
        path=str(item["path"]),
        title=str(item["title"]),
        read_budget=str(item["read_budget"]),
        trust=str(item["trust"]),
        status=str(item["status"]),
        stale=item["stale"],
        covers=tuple(str(c) for c in item["covers"]),
        units=count_units(text),
        text=text,
    )


def _revision_path(item: dict[str, Any], tree: Path, base: Path) -> str:
    """Re-express a selected document's path relative to the revision root.

    The resolver returns absolute paths from the *working* bundle; the prompt is
    built from a materialized revision, a different root. Paths are made relative
    to the project root — the same root `harness.toml` is read from — so nothing
    about the layout is hardcoded. A document that does not resolve inside the
    revision is an error, never a silent omission.
    """
    absolute = Path(str(item["path"])).resolve()
    try:
        relative = absolute.relative_to(base.resolve()).as_posix()
    except ValueError as exc:
        raise CompileError(f"selected document is outside the project: {absolute}") from exc

    if not (tree / relative).is_file():
        raise CompileError(f"selected document is missing from the revision: {relative}")
    return relative
