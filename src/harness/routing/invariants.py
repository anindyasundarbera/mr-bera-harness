#!/usr/bin/env python3
"""Validate a project's routing invariants.

These are the checks that make `DOCUMENT_ROUTING.md` section 5 a test rather
than a hope. They are deliberately separate from `tools/okf.py`, which checks
OKF v0.2 conformance (a format question); this tool checks the MrBera routing
extensions (a governance question).

Checks:
  1. Frontmatter parses as the leading block only (examples in prose are ignored).
  2. Required routing fields present; no prohibited status/value field leaks in.
  3. At most one `canonical: true` per (module, class).
  4. Every `covers` decomposition ID exists in PROJECT_DECOMPOSITION.md.
  5. Every `module` exists in MODULE_REGISTRY.md.
  6. No `do_not_use_for` state-ownership key is claimed by two modules.
  7. Every `depends_on` target resolves to an existing document or concept.
  8. `id` matches the document's `> ID:` line where both are present.

Exit codes: 0 = clean, 1 = violations found, 2 = usage error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.config import Config
from harness.okf import Bundle, OkfError, split_frontmatter


def _defaults(config: Config) -> tuple[Path, Path, Path]:
    """Derive the project's document locations from its configuration."""
    docs = config.path("docs")
    return config.path("knowledge"), docs / "PROJECT_DECOMPOSITION.md", docs / "MODULE_REGISTRY.md"


# Routing facts only.
#
# Note on `status`: OKF itself defines `status: draft|stable|deprecated` as a
# DOCUMENT LIFECYCLE field (SPEC section 5.4). That is not a decision status and
# is allowed here. What must never appear is a *decision* status — those live in
# DECISION_REGISTRY.md.
PROHIBITED_KEYS = frozenset(
    {"decision_status", "decision", "value", "threshold", "version", "updated", "date"}
)

# `state` is permitted only on an Unknown concept, where it mirrors GAP_REGISTER
# and is validated against it by check 9 (so it cannot drift).
STATE_ALLOWED_TYPES = frozenset({"Unknown"})

# OKF's lifecycle enum (SPEC section 5.4). Some concept types carry their own
# status vocabulary, because their status is an editorial state rather than a
# document lifecycle state. `status` is never a *decision* status either way —
# that lives in DECISION_REGISTRY.md and is prohibited from frontmatter.
OKF_LIFECYCLE = frozenset({"draft", "stable", "deprecated"})
STATUS_VOCABULARY_BY_TYPE: dict[str, frozenset[str]] = {
    "Decision Record": frozenset(
        {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded", "ArchitectureSelected"}
    ),
}


def allowed_statuses(concept_type: str) -> frozenset[str]:
    """The set of legal `status` values for a concept type."""
    return STATUS_VOCABULARY_BY_TYPE.get(concept_type, OKF_LIFECYCLE)


MODULE_ID_RE = re.compile(r"MRB-M\d{2}")
DOC_ID_RE = re.compile(r"^> ID:\s*(\S+)\s*$", re.MULTILINE)

# Subtrees governed by a different validator. Routing invariants apply to
# module-scoped specifications; changelog and ADR entries have their own schema
# and are checked by tools/entries.py. One artifact class, one validator —
# otherwise a rule written for one class produces false failures in another.
FOREIGN_SCHEMA_PREFIXES = ("changelog/", "decisions/")


@dataclass
class Violation:
    check: int
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[check {self.check}] {self.subject}: {self.detail}"


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def add(self, check: int, subject: str, detail: str) -> None:
        self.violations.append(Violation(check, subject, detail))


def known_decomposition_ids(path: Path) -> set[str]:
    """Decomposition IDs that actually appear in PROJECT_DECOMPOSITION.md."""
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    ids = set(re.findall(r"MRB-M\d{2}(?:-S\d{2}(?:-C\d{2}(?:-W\d{2}(?:-A\d{2})?)?)?)?", text))
    # The module prefixes themselves are always valid scopes.
    ids |= set(MODULE_ID_RE.findall(text))
    return ids


def known_modules(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(MODULE_ID_RE.findall(path.read_text(encoding="utf-8")))


GAP_ROW_RE = re.compile(r"^\|\s*(GAP-[A-Z]+-\d{3})\s*\|", re.MULTILINE)

# The state vocabulary from GAP_REGISTER.md section 1.
GAP_STATE_VOCAB = (
    "ImplementedUnvalidated",
    "BlockedDependency",
    "BlockedExternal",
    "BlockedOwner",
    "InProgress",
    "Specified",
    "Validated",
    "Deferred",
    "Open",
)


def gap_states(config: Config, path: Path | None = None) -> dict[str, str]:
    """Map gap ID -> state, read from GAP_REGISTER.md.

    Column order varies between the register's tables, so the state is found by
    vocabulary rather than by position. This is what lets an Unknown concept
    mirror a gap state without being able to drift from it: validate_routing
    check 9 compares the two.
    """
    path = path or (config.path("docs") / "GAP_REGISTER.md")
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = GAP_ROW_RE.match(line)
        if not match:
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        for cell in cells:
            if cell in GAP_STATE_VOCAB:
                states[match.group(1)] = cell
                break
    return states


def validate(
    bundle_dir: Path,
    decomposition_ids: set[str] | None = None,
    modules: set[str] | None = None,
    gaps: dict[str, str] | None = None,
) -> Report:
    """Run the routing checks over a bundle."""
    report = Report()
    # Callers supply these from configuration. The standalone version resolved
    # them from module-level constants, which is why the no-argument form existed;
    # leaving it would have raised at runtime for any caller that omitted them.
    decomposition_ids = decomposition_ids or set()
    modules = modules or set()
    gap_states_map = gaps if gaps is not None else {}

    try:
        bundle = Bundle(bundle_dir)
        concepts = bundle.concepts()
    except OkfError as exc:
        report.add(1, str(bundle_dir), f"bundle unreadable: {exc}")
        return report

    owners: dict[str, set[str]] = {}
    canonical_seen: dict[tuple[str, str], str] = {}

    for cid, concept in sorted(concepts.items()):
        if cid.startswith(FOREIGN_SCHEMA_PREFIXES):
            continue  # validated by tools/entries.py, not by routing rules
        report.checked += 1
        fm = concept.frontmatter
        module = str(fm.get("module", ""))
        klass = str(fm.get("class", "") or fm.get("type", ""))

        # Check 2: prohibited keys never appear in frontmatter.
        for key in PROHIBITED_KEYS:
            if key in fm:
                report.add(2, cid, f"prohibited frontmatter key `{key}` (routing facts only)")
        if "state" in fm and concept.type not in STATE_ALLOWED_TYPES:
            report.add(2, cid, f"`state` is only permitted on type Unknown, not {concept.type}")

        # Check 2b: `status`, when present, must be legal for this concept type.
        raw_status = fm.get("status")
        if raw_status is not None:
            permitted = allowed_statuses(concept.type)
            if str(raw_status) not in permitted:
                report.add(
                    2,
                    cid,
                    f"status `{raw_status}` is not legal for type `{concept.type}` "
                    f"({'|'.join(sorted(permitted))})",
                )

        # Check 9: an Unknown's `state` must match the gap register, so the
        # mirror cannot drift from the authority.
        if concept.type in STATE_ALLOWED_TYPES and "state" in fm:
            gap_id = str(fm.get("gap", ""))
            declared = str(fm["state"])
            if gap_id:
                if not gap_states_map:
                    # Fail loudly: a check that silently skips because it cannot
                    # read the authority is worse than no check at all.
                    report.add(
                        9,
                        cid,
                        "cannot verify state: GAP_REGISTER.md unreadable or yielded no states",
                    )
                else:
                    actual = gap_states_map.get(gap_id)
                    if actual is None:
                        report.add(9, cid, f"gap `{gap_id}` not found in GAP_REGISTER.md")
                    elif actual != declared:
                        report.add(
                            9,
                            cid,
                            f"state `{declared}` disagrees with GAP_REGISTER.md "
                            f"(`{gap_id}` is `{actual}`)",
                        )

        # Check 3: one canonical per (module, class).
        if fm.get("canonical") is True:
            slot = (module, klass)
            if slot in canonical_seen:
                report.add(
                    3,
                    cid,
                    f"duplicate canonical:true for ({module}, {klass}); "
                    f"already claimed by {canonical_seen[slot]}",
                )
            else:
                canonical_seen[slot] = cid

        # Check 4: covers IDs must exist in the decomposition.
        for raw_covered in fm.get("covers") or []:
            covered = str(raw_covered)
            if covered == "MRB":
                continue  # project-wide scope
            if decomposition_ids and covered not in decomposition_ids:
                report.add(4, cid, f"covers `{covered}` not found in PROJECT_DECOMPOSITION.md")

        # Check 5: module must be registered (skip framework-level concepts).
        if modules and module and module not in modules and module != "MRB-LRF":
            report.add(5, cid, f"module `{module}` not found in MODULE_REGISTRY.md")

        # Check 6: ownership keys must be unique per module.
        for key in fm.get("do_not_use_for") or []:
            owners.setdefault(str(key), set()).add(owners_key(module, concept))

    for key, claimants in sorted(owners.items()):
        if len(claimants) > 1:
            # A single module holding one key across several concepts is fine;
            # two modules claiming the same key is a conflict.
            distinct_modules = {c.split(":")[0] for c in claimants}
            if len(distinct_modules) > 1:
                report.add(
                    6,
                    key,
                    f"claimed by multiple modules: {', '.join(sorted(distinct_modules))}",
                )

    return report


def owners_key(module: str, concept: Any) -> str:
    """Identify the claiming module for an ownership key.

    An `owner_module` key, when present, states which module actually owns the
    state; otherwise the concept's own `module` is the claimant.
    """
    owning = concept.frontmatter.get("owner_module") or module
    return f"{owning}:{concept.concept_id}"


def validate_routing(config: Config) -> Report:
    """Run every routing invariant for a configured project."""
    bundle_dir, decomposition, module_registry = _defaults(config)
    report = validate(
        bundle_dir,
        known_decomposition_ids(decomposition),
        known_modules(module_registry),
        gap_states(config),
    )
    check_doc_frontmatter(report, config.path("docs"))
    return report


def check_doc_frontmatter(report: Report, docs_dir: Path) -> None:
    """Check 7-8 over the markdown documents that carry routing frontmatter."""
    if not docs_dir.exists():
        return
    for md in sorted(docs_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue  # a doc without frontmatter is do-not-load, not an error
        try:
            fm, _ = split_frontmatter(text)
        except OkfError as exc:
            report.add(1, md.name, f"malformed frontmatter: {exc}")
            continue

        # Check 8: id must match the document's own `> ID:` line when present.
        doc_id = DOC_ID_RE.search(text)
        fm_id = fm.get("id")
        if doc_id and fm_id and str(fm_id) != doc_id.group(1):
            report.add(8, md.name, f"frontmatter id `{fm_id}` != document ID `{doc_id.group(1)}`")

        # Check 7: depends-on targets must resolve.
        for raw_target in fm.get("depends-on") or []:
            target = str(raw_target)
            candidate = docs_dir / target
            if (
                not candidate.exists()
                and not (docs_dir / target.rsplit("/", maxsplit=1)[-1]).exists()
            ):
                report.add(7, md.name, f"depends-on target `{target}` does not resolve")
