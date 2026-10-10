"""Resolve the exact document set that binds a work item.

This is the heart of the harness's token saving: it answers "which documents do
I need?" with a set intersection rather than a model judgement, so most agent
questions never reach an LLM at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from harness.okf import Bundle, Concept
from harness.routing.chain import parent_chain

if TYPE_CHECKING:
    from harness.config import Config

READ_ORDER = {"must-read": 0, "reference-only": 1, "do-not-load": 2}
STOP_CONCEPT_TYPE = "Unknown"


@dataclass
class ResolvedContext:
    """The outcome of routing: what to load, what to avoid, and where to stop."""

    work_id: str
    chain: list[str]
    load: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    stop_conditions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def must_stop(self) -> bool:
        """True when work must not proceed, for either reason."""
        return bool(self.stop_conditions) or not self.load

    def exit_code(self) -> int:
        """0 resolved, 3 named blocker, 4 uncovered chain."""
        if self.stop_conditions:
            return 3
        if not self.load:
            return 4
        return 0


def _covers(concept: Concept) -> list[str]:
    return [str(x) for x in (concept.frontmatter.get("covers") or [])]


def _do_not_use_for(concept: Concept) -> list[str]:
    # Accept both the hyphenated and underscored spellings so a project can use
    # whichever its frontmatter style prefers.
    raw = concept.frontmatter.get("do_not_use_for")
    if raw is None:
        raw = concept.frontmatter.get("do-not-use-for")
    return [str(x) for x in (raw or [])]


def _blocks(concept: Concept) -> list[str]:
    return [str(x) for x in (concept.frontmatter.get("blocks") or [])]


def _read_budget(concept: Concept) -> str:
    raw = concept.frontmatter.get("read_budget") or concept.frontmatter.get("read-budget")
    return str(raw or "must-read")


def resolve_context(
    config: Config,
    work_id: str,
    *,
    defining: list[str] | None = None,
    bundle: Bundle | None = None,
) -> ResolvedContext:
    """Select the concepts that bind `work_id`.

    A concept is selected when its `covers` intersects the parent chain, and
    excluded when its `do_not_use_for` names a state the caller intends to define.
    `Unknown` concepts are surfaced only as stop conditions, never as content.
    """
    defining = defining or []
    chain = parent_chain(work_id, config.identity)
    scope = set(chain) | {work_id}

    bundle = bundle or Bundle(config.path("knowledge"))
    concepts = bundle.concepts()

    result = ResolvedContext(work_id=work_id, chain=chain)
    selected: list[Concept] = []

    for concept in concepts.values():
        covers = _covers(concept)
        if not covers or not (set(covers) & set(chain)):
            continue
        blocked = sorted(set(_do_not_use_for(concept)) & set(defining))
        if blocked:
            result.excluded.append({"concept_id": concept.concept_id, "reason": blocked})
        elif concept.type != STOP_CONCEPT_TYPE:
            selected.append(concept)

    selected.sort(key=lambda c: (READ_ORDER.get(_read_budget(c), 9), c.concept_id))
    result.load = [
        {
            "concept_id": c.concept_id,
            "path": str(c.path),
            "type": c.type,
            "title": c.title,
            "read_budget": _read_budget(c),
            "covers": _covers(c),
            "trust": c.trust_tier,
            "status": c.status,
            "stale": c.is_stale(),
        }
        for c in selected
        if _read_budget(c) != "do-not-load"
    ]

    stops = [
        c for c in concepts.values() if c.type == STOP_CONCEPT_TYPE and set(_blocks(c)) & scope
    ]
    stops.sort(key=lambda c: c.concept_id)
    result.stop_conditions = [
        {
            "concept_id": c.concept_id,
            "path": str(c.path),
            "title": c.title,
            "state": c.frontmatter.get("state"),
            "blocker": c.frontmatter.get("blocker"),
            "blocks": _blocks(c),
            "if_you_guess": c.frontmatter.get("if_you_guess"),
            "must_not_do": c.frontmatter.get("must_not_do") or [],
        }
        for c in stops
    ]
    return result


def render(context: ResolvedContext) -> str:
    """Human-readable form, used by the CLI and in tests."""
    lines = [
        f"work item : {context.work_id}",
        f"chain     : {' > '.join(context.chain)}",
        "",
        f"LOAD ({len(context.load)} concept(s))",
    ]
    if not context.load:
        lines.append(
            "  (none) — no concept covers this chain. Record BlockedDependency; do not invent."
        )
    for item in context.load:
        flags = [f"trust={item['trust']}", item["read_budget"]]
        if item["stale"]:
            flags.insert(0, "STALE")
        lines.append(f"  - {item['concept_id']}  [{item['type']}]  {' '.join(flags)}")
        lines.append(f"      {item['path']}")
    if context.excluded:
        lines += ["", f"EXCLUDED ({len(context.excluded)}) — must not be used to define your state"]
        for item in context.excluded:
            lines.append(f"  - {item['concept_id']}  ({','.join(item['reason'])})")
    lines.append("")
    if context.stop_conditions:
        lines.append(
            f"STOP CONDITIONS ({len(context.stop_conditions)}) — record the blocker, do not guess"
        )
        for item in context.stop_conditions:
            lines.append(f"  - {item['title']}  [{item['state']}]  blocker={item['blocker']}")
            if item["if_you_guess"]:
                lines.append(f"      if you guess: {item['if_you_guess']}")
            for rule in item["must_not_do"]:
                lines.append(f"      must not: {rule}")
    else:
        lines.append("STOP CONDITIONS: none for this chain.")
    return "\n".join(lines)


def bundle_path(config: Config) -> Path:
    return config.path("knowledge")
