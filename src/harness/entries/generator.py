#!/usr/bin/env python3
"""Validate and index the changelog and ADR entry files.

Design
------
The authoritative changelog is a **directory of entry files**, one per change —
never a single shared append-target. Two branches therefore cannot conflict,
because they never touch the same file.

`CHANGELOG.md` and `docs/DECISIONS_INDEX.md` are **derived views** generated from
those entries. Regeneration is idempotent; hand-editing a generated file is a
defect, because the next run overwrites it.

Entry frontmatter is validated against the schema below and fails loudly, rather
than silently dropping an entry from the generated output.

Usage
-----
    python3 tools/entries.py validate            # schema + uniqueness checks
    harness entries generate            # rewrite the two index files
    harness entries generate --check    # fail if regeneration would change

Exit codes: 0 = clean, 1 = problems, 2 = usage error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.okf import OkfError, parse_timestamp, split_frontmatter


def default_project_root() -> Path:
    """The project the command was invoked in, not the harness's own location.

    This was `Path(__file__).resolve().parents[3]`, which resolves to the
    *harness* repository. Running `harness entries generate` inside a consumer
    therefore wrote `CHANGELOG.md` and `docs/DECISIONS_INDEX.md` into the
    harness's own working tree — silently modifying a different repository. The
    current working directory is the only correct answer.
    """
    return Path.cwd()


def _default_dirs() -> tuple[Path, Path]:
    """Entry directories, taken from the project's own `harness.toml`."""
    from harness.config import load_config  # noqa: PLC0415 - deferred to avoid a cycle

    config = load_config(default_project_root())
    return config.path("changelog"), config.path("decisions")


def _default_targets() -> tuple[Path, Path]:
    """Generated-file locations, taken from the project's own `harness.toml`."""
    from harness.config import load_config  # noqa: PLC0415 - deferred to avoid a cycle

    config = load_config(default_project_root())
    return config.root / "CHANGELOG.md", config.path("docs") / "DECISIONS_INDEX.md"


CHANGELOG_KINDS = frozenset({"added", "changed", "fixed", "removed", "deprecated", "security"})
ADR_STATUSES = frozenset(
    {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded", "ArchitectureSelected"}
)

ENTRY_ID_RE = re.compile(r"\A(?:CHG|ADR)-\d{4}-\d{2,3}\Z")
DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


@dataclass
class Problem:
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.path.name}: {self.detail}"


@dataclass
class Entry:
    """One changelog or ADR entry."""

    path: Path
    frontmatter: dict[str, Any]
    body: str
    kind: str = "changelog"  # "changelog" | "adr"

    @property
    def id(self) -> str:
        return str(self.frontmatter.get("id", ""))

    @property
    def date(self) -> str:
        return str(self.frontmatter.get("date", ""))

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title", ""))

    @property
    def summary(self) -> str:
        return str(self.frontmatter.get("summary", ""))

    @property
    def covers(self) -> list[str]:
        return [str(x) for x in (self.frontmatter.get("covers") or [])]


@dataclass
class ValidationResult:
    problems: list[Problem] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def load_entries(directory: Path, kind: str) -> tuple[list[Entry], list[Problem]]:
    """Load every `.md` entry in a directory, sorted newest first."""
    entries: list[Entry] = []
    problems: list[Problem] = []
    if not directory.exists():
        return entries, problems
    for path in sorted(directory.glob("*.md")):
        if path.name == "index.md":
            continue  # the directory's own index, not an entry
        try:
            frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except OkfError as exc:
            problems.append(Problem(path, f"malformed frontmatter: {exc}"))
            continue
        entries.append(Entry(path=path, frontmatter=frontmatter, body=body, kind=kind))
    entries.sort(key=lambda e: (e.date, e.id), reverse=True)
    return entries, problems


def validate_changelog_entry(entry: Entry) -> list[Problem]:
    problems: list[Problem] = []

    def bad(detail: str) -> None:
        problems.append(Problem(entry.path, detail))

    if not ENTRY_ID_RE.match(entry.id) or not entry.id.startswith("CHG-"):
        bad(f"id `{entry.id}` must match CHG-YYYY-NNN")

    if not DATE_RE.match(entry.date):
        bad(f"date `{entry.date}` must be YYYY-MM-DD")
    else:
        try:
            parse_timestamp(f"{entry.date}T00:00:00Z")
        except (OkfError, ValueError):
            bad(f"date `{entry.date}` is not a real calendar date")

    if not entry.title:
        bad("`title` is required")
    if not entry.summary:
        bad("`summary` is required")

    kind_value = str(entry.frontmatter.get("kind", ""))
    if kind_value not in CHANGELOG_KINDS:
        bad(f"kind `{kind_value}` must be one of {'|'.join(sorted(CHANGELOG_KINDS))}")

    # `covers` reuses the routing vocabulary so a changelog entry can be routed
    # to the module it concerns.
    if not entry.covers:
        bad("`covers` is required (at least one module or workflow ID)")

    return problems


def validate_adr_entry(entry: Entry) -> list[Problem]:
    problems: list[Problem] = []

    def bad(detail: str) -> None:
        problems.append(Problem(entry.path, detail))

    if not ENTRY_ID_RE.match(entry.id) or not entry.id.startswith("ADR-"):
        bad(f"id `{entry.id}` must match ADR-YYYY-NNN")

    if not DATE_RE.match(entry.date):
        bad(f"date `{entry.date}` must be YYYY-MM-DD")

    if not entry.title:
        bad("`title` is required")

    status = str(entry.frontmatter.get("status", ""))
    if status not in ADR_STATUSES:
        bad(f"status `{status}` must be one of {'|'.join(sorted(ADR_STATUSES))}")

    if not entry.frontmatter.get("decision"):
        bad("`decision` is required (one-sentence statement of what was decided)")

    supersedes = entry.frontmatter.get("supersedes")
    if supersedes is not None and not isinstance(supersedes, list):
        bad("`supersedes` must be a list when present")

    return problems


def validate_all(
    changelog_dir: Path | None = None, decisions_dir: Path | None = None
) -> ValidationResult:
    """Validate every entry and check global uniqueness."""
    if changelog_dir is None or decisions_dir is None:
        default_changelog, default_decisions = _default_dirs()
        changelog_dir = changelog_dir or default_changelog
        decisions_dir = decisions_dir or default_decisions

    result = ValidationResult()

    changes, problems = load_entries(changelog_dir, "changelog")
    result.problems.extend(problems)
    adrs, problems = load_entries(decisions_dir, "adr")
    result.problems.extend(problems)
    result.entries = changes + adrs

    for entry in changes:
        result.problems.extend(validate_changelog_entry(entry))
    for entry in adrs:
        result.problems.extend(validate_adr_entry(entry))

    # IDs must be globally unique: a duplicate means two branches claimed one.
    seen: dict[str, Path] = {}
    for entry in result.entries:
        if entry.id in seen:
            result.problems.append(
                Problem(entry.path, f"duplicate id `{entry.id}` (also in {seen[entry.id].name})")
            )
        else:
            seen[entry.id] = entry.path

    # An ADR may only supersede an ADR that exists.
    known_adr_ids = {a.id for a in adrs}
    for adr in adrs:
        for target in adr.frontmatter.get("supersedes") or []:
            if str(target) not in known_adr_ids:
                result.problems.append(
                    Problem(adr.path, f"supersedes `{target}`, which does not exist")
                )

    return result


def render_changelog(entries: list[Entry]) -> str:
    """Render CHANGELOG.md from changelog entries, newest first."""
    lines = [
        "# Changelog",
        "",
        "> **Generated file — do not edit by hand.**",
        "> Regenerate with `harness entries generate`.",
        "> The authoritative entries live in `knowledge/changelog/`.",
        "",
    ]
    by_date: dict[str, list[Entry]] = {}
    for entry in entries:
        by_date.setdefault(entry.date, []).append(entry)

    for date in sorted(by_date, reverse=True):
        lines.append(f"## {date}")
        lines.append("")
        for entry in by_date[date]:
            kind = str(entry.frontmatter.get("kind", ""))
            lines.append(f"### {kind.capitalize()}: {entry.title}")
            lines.append("")
            lines.append(f"*{entry.summary}*")
            lines.append("")
            covers = ", ".join(f"`{c}`" for c in entry.covers)
            lines.append(f"- **ID:** `{entry.id}`  ")
            if entry.frontmatter.get("pr"):
                lines.append(f"- **PR:** #{entry.frontmatter['pr']}  ")
            if entry.frontmatter.get("branch"):
                lines.append(f"- **Branch:** `{entry.frontmatter['branch']}`  ")
            lines.append(f"- **Covers:** {covers}")
            lines.append("")
            body = entry.body.strip()
            if body:
                lines.append(body)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_decisions_index(entries: list[Entry]) -> str:
    """Render the ADR index from ADR entries, newest first."""
    lines = [
        "# Architecture Decision Index",
        "",
        "> **Generated file — do not edit by hand.**",
        "> Regenerate with `harness entries generate`.",
        "> The authoritative entries live in `knowledge/decisions/`.",
        "",
        "| ID | Date | Title | Status | Supersedes |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        status = str(entry.frontmatter.get("status", ""))
        supersedes = ", ".join(f"`{s}`" for s in (entry.frontmatter.get("supersedes") or []))
        lines.append(
            f"| `{entry.id}` | {entry.date} | {entry.title} | {status} | {supersedes or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate(
    *,
    check: bool = False,
    changelog_dir: Path | None = None,
    decisions_dir: Path | None = None,
    changelog_md: Path | None = None,
    decisions_index_md: Path | None = None,
) -> tuple[int, list[str]]:
    """Write (or verify) the generated index files. Returns (exit_code, messages).

    Directories and targets are injectable so generation can be tested against a
    temporary tree rather than the live repository. When omitted, both are read
    from the invoking project's `harness.toml`.
    """
    if changelog_md is None or decisions_index_md is None:
        default_changelog_md, default_index_md = _default_targets()
        changelog_md = changelog_md or default_changelog_md
        decisions_index_md = decisions_index_md or default_index_md

    result = validate_all(changelog_dir, decisions_dir)
    if not result.ok:
        return 1, [str(p) for p in result.problems]

    changes = [e for e in result.entries if e.kind == "changelog"]
    adrs = [e for e in result.entries if e.kind == "adr"]

    targets = {
        changelog_md: render_changelog(changes),
        decisions_index_md: render_decisions_index(adrs),
    }

    messages: list[str] = []
    drifted = False
    for path, content in targets.items():
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        if check:
            if existing != content:
                drifted = True
                messages.append(f"{_display(path)}: out of date")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        messages.append(f"{_display(path)}: written ({len(content)} bytes)")

    if check:
        if drifted:
            return 1, messages
        messages.append("generated files are up to date")
    return 0, messages


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(default_project_root()))
    except ValueError:
        return str(path)
