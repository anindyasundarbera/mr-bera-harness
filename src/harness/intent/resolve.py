"""Resolve a human instruction to candidate work items — explicitly and fallibly.

Build-order step 6 of `HARNESS_ARCHITECTURE.md` §9 is the one step rated **not
deterministic**, and §8 states what can honestly be built:

> Fully deterministic instruction→prompt | Intent classification is fuzzy |
> **Deterministic prompt *assembly*; intent resolution is explicit and fallible,
> with a human-clarification fallback**

So this module does **not** classify intent. It does three things:

1. Extracts work identifiers an instruction **already contains** — exact, not fuzzy.
2. Scores every identifier in the project for lexical similarity, so a mention of
   "model set" can surface `MRB-M06-S03`.
3. **Refuses when the answer is not unambiguous.** Two close candidates, or none,
   is a clarification request — never a pick.

The refusal is the feature. §9 says the design must not depend on this step — "a
human who writes the task ID directly bypasses step 6 entirely and loses nothing" —
so a wrong guess would be strictly worse than no answer, because it would compile a
prompt bound to the wrong work item and say so confidently.

Nothing here calls a model. The scoring is lexical and deterministic; a semantic
resolver would be a different, non-reproducible thing, and is not this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from harness.okf import Bundle

if TYPE_CHECKING:
    from pathlib import Path

    from harness.config import Config

#: How an instruction was resolved. Three-valued, like every other verdict here:
#: "unresolved" is not "no match", it is "no single answer".
RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"

#: Exit codes, part of the command's contract.
EXIT_OK = 0
EXIT_AMBIGUOUS = 3
EXIT_UNRESOLVED = 4

#: Words too common to carry signal when scoring a title or concept id.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "why",
        "with",
    }
)

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class Candidate:
    """One work identifier a project declares, with what it is called."""

    work_id: str
    title: str = ""
    concepts: tuple[str, ...] = ()
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "work_id": self.work_id,
            "title": self.title,
            "score": round(self.score, 4),
            "concepts": list(self.concepts),
        }


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one instruction."""

    instruction: str
    status: str
    chosen: str | None = None
    candidates: tuple[Candidate, ...] = ()
    exact: tuple[str, ...] = ()
    reason: str = ""

    @property
    def must_clarify(self) -> bool:
        return self.status != RESOLVED

    def exit_code(self) -> int:
        if self.status == RESOLVED:
            return EXIT_OK
        return EXIT_AMBIGUOUS if self.status == AMBIGUOUS else EXIT_UNRESOLVED

    def as_dict(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "status": self.status,
            "chosen": self.chosen,
            "exact": list(self.exact),
            "reason": self.reason,
            "candidates": [c.as_dict() for c in self.candidates],
        }


def _tokens(text: str) -> list[str]:
    """Lower-cased content words, for lexical comparison only."""
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) > 1 and w.lower() not in _STOPWORDS]


def scan_pattern(config: Config) -> re.Pattern[str]:
    """An **unanchored** pattern for finding identifiers inside text.

    `identity.id_pattern()` is anchored (`\\A…\\Z`) because it *validates* a whole
    identifier. Scanning prose needs the same grammar without the anchors —
    `re.search` with an anchored pattern can never match a substring, which is why
    an instruction naming `MRB-M06-S07` initially resolved to nothing.

    The optional groups must **nest**, exactly as the validating grammar does: each
    level is required relative to its parent, so `MRB-M06` matches and no level is
    skipped. Concatenating them instead would make every level mandatory, and the
    pattern would then match almost nothing.
    """
    identity = config.identity
    levels = [
        rf"(?:-{re.escape(m)}\d{{{w}}})"
        for m, w in zip(identity.levels, identity.widths, strict=False)
    ]
    body = ""
    for level in reversed(levels[1:]):
        body = f"(?:{level}{body})?"
    return re.compile(rf"{re.escape(identity.id_prefix)}{levels[0]}{body}")


def exact_mentions(instruction: str, pattern: re.Pattern[str]) -> list[str]:
    """Work identifiers the instruction already contains, in first-seen order.

    An identifier the caller wrote is not a guess: the configured grammar decides
    it, so this is exact rather than fuzzy.
    """
    found: list[str] = []
    for match in pattern.finditer(instruction):
        value = match.group(0)
        if value not in found:
            found.append(value)
    return found


def known_work_ids(config: Config, *, decomposition: Path | None = None) -> dict[str, str]:
    """Every work identifier the project declares, mapped to a title.

    Identifiers come from the decomposition document — the project's own declaration
    of what work exists — never from an invented list. A project without one gets an
    empty map, and resolution then has nothing to offer, which is the honest result.
    """
    path = decomposition or (config.path("docs") / "PROJECT_DECOMPOSITION.md")
    if not path.is_file():
        return {}

    text = path.read_text(encoding="utf-8")
    pattern = scan_pattern(config)
    titles: dict[str, str] = {}
    for line in text.splitlines():
        found = pattern.search(line)
        if not found:
            continue
        work_id = found.group(0)
        # The remainder of the line is the title, stripped of markdown bullets.
        title = line[found.end() :].lstrip(" \t:—-").strip()
        titles.setdefault(work_id, title)
    return titles


def concepts_by_work_id(config: Config) -> dict[str, tuple[str, ...]]:
    """Which concepts cover each work identifier, read from the bundle.

    This is what lets a phrase reach an identifier: a mention of "model set" scores
    against the *concept titles* that cover `MRB-M06-S03`, not only against the
    identifier's own title.
    """
    knowledge = config.path("knowledge")
    if not knowledge.is_dir():
        return {}

    mapping: dict[str, list[str]] = {}
    for concept in Bundle(knowledge).concepts().values():
        covers = [str(c) for c in (concept.frontmatter.get("covers") or [])]
        for work_id in covers:
            mapping.setdefault(work_id, []).append(concept.title)
    return {k: tuple(sorted(set(v))) for k, v in mapping.items()}


def score(instruction: str, candidate: Candidate) -> float:
    """A lexical score in [0, 1]. Deterministic: the same inputs give the same number.

    Deliberately simple and explainable — Jaccard overlap over content words. A
    cleverer scorer would be harder to explain to the person being asked to clarify,
    and explainability is the point when the fallback is a question.
    """
    asked = set(_tokens(instruction))
    if not asked:
        return 0.0

    described = set(_tokens(candidate.title))
    for concept in candidate.concepts:
        described |= set(_tokens(concept))
    if not described:
        return 0.0

    return len(asked & described) / len(asked | described)


def resolve(
    config: Config,
    instruction: str,
    *,
    decomposition: Path | None = None,
    threshold: float = 0.2,
) -> Resolution:
    """Resolve an instruction to one work item, or say why it cannot.

    `threshold` is the minimum score a candidate must reach to be considered. It is
    a parameter with a documented default because it is a *relevance* cut, not a
    decision threshold that authorises anything: a wrong cut costs a clarification
    question, and nothing executes either way.

    Resolution is `resolved` only when there is exactly one answer:

    * an identifier written in the instruction — if exactly one, use it;
    * otherwise, candidates above the threshold — if exactly one, use it;
    * several close candidates is `ambiguous`, and **no winner is chosen**;
    * none is `unresolved`.
    """
    pattern = scan_pattern(config)
    exact = exact_mentions(instruction, pattern)

    titles = known_work_ids(config, decomposition=decomposition)
    concepts = concepts_by_work_id(config)

    if len(exact) == 1:
        work_id = exact[0]
        known = work_id in titles
        return Resolution(
            instruction=instruction,
            status=RESOLVED,
            chosen=work_id,
            exact=tuple(exact),
            reason=(
                "the instruction names exactly one work identifier"
                if known
                else "the instruction names exactly one work identifier, which the "
                "decomposition does not declare; it may be new work"
            ),
        )
    if len(exact) > 1:
        # More than one identifier written down is a real ambiguity, and picking one
        # would be exactly the guess this step exists to refuse.
        return Resolution(
            instruction=instruction,
            status=AMBIGUOUS,
            exact=tuple(exact),
            reason=f"the instruction names {len(exact)} work identifiers; ask which",
        )

    scored = [
        Candidate(
            work_id=work_id,
            title=title,
            concepts=concepts.get(work_id, ()),
        )
        for work_id, title in titles.items()
    ]
    scored = [Candidate(c.work_id, c.title, c.concepts, score(instruction, c)) for c in scored]
    above = sorted((c for c in scored if c.score >= threshold), key=lambda c: (-c.score, c.work_id))

    if not above:
        return Resolution(
            instruction=instruction,
            status=UNRESOLVED,
            candidates=tuple(sorted(scored, key=lambda c: (-c.score, c.work_id))[:5]),
            reason=(
                "no work identifier is named and nothing in the decomposition scores "
                f"at or above {threshold}; name the work item rather than guessing"
            ),
        )

    best = above[0]
    tied = [c for c in above if c.score == best.score]
    if len(tied) > 1:
        return Resolution(
            instruction=instruction,
            status=AMBIGUOUS,
            candidates=tuple(tied[:5]),
            reason=(
                f"{len(tied)} work items score identically ({best.score:.2f}); "
                "ask which, rather than picking one"
            ),
        )

    # A clear leader is still not a decision: a runner-up close behind means the
    # instruction could reasonably mean either, so it is a question.
    if len(above) > 1 and above[1].score >= best.score * 0.8:
        return Resolution(
            instruction=instruction,
            status=AMBIGUOUS,
            candidates=tuple(above[:5]),
            reason=(
                f"`{best.work_id}` leads on {best.score:.2f} but `{above[1].work_id}` "
                f"is close on {above[1].score:.2f}; ask which"
            ),
        )

    return Resolution(
        instruction=instruction,
        status=RESOLVED,
        chosen=best.work_id,
        candidates=tuple(above[:5]),
        reason=f"exactly one work item scored at or above {threshold} ({best.score:.2f})",
    )


def render(resolution: Resolution, config: Config, *, limit: int = 5) -> str:  # noqa: ARG001
    """Human-readable form, used by the CLI and in tests.

    `config` is accepted for a uniform call signature with the other renderers; the
    resolution already carries everything needed to display.
    """
    lines = [
        f"instruction : {resolution.instruction}",
        f"status      : {resolution.status}",
    ]
    if resolution.chosen:
        lines.append(f"work item   : {resolution.chosen}")
    lines.append(f"reason      : {resolution.reason}")
    if resolution.candidates:
        lines.append("")
        lines.append(f"candidates ({min(limit, len(resolution.candidates))})")
        for candidate in resolution.candidates[:limit]:
            lines.append(
                f"  {candidate.work_id:<20} {candidate.score:>5.2f}  {candidate.title[:56]}"
            )
    if resolution.must_clarify:
        lines += [
            "",
            "Ask the person which work item this means, or name it explicitly:",
            f'  harness intent resolve "{resolution.instruction}" --work-id <ID>',
        ]
    return "\n".join(lines)
