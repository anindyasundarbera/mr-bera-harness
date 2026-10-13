"""Resolve a human instruction to candidate work items — explicitly and fallibly.

Build-order step 6 of `HARNESS_ARCHITECTURE.md` §9, the one step rated **not
deterministic**. §8 states what can honestly be built: *deterministic prompt
assembly; intent resolution is explicit and fallible, with a human-clarification
fallback*.

So this package does not classify intent. It finds work identifiers an instruction
already names, scores the alternatives lexically, and **refuses when the answer is
not unique** — because a wrong guess would compile a prompt bound to the wrong work
item and say so confidently.
"""

from harness.intent.resolve import (
    AMBIGUOUS,
    EXIT_AMBIGUOUS,
    EXIT_OK,
    EXIT_UNRESOLVED,
    RESOLVED,
    UNRESOLVED,
    Candidate,
    Resolution,
    concepts_by_work_id,
    exact_mentions,
    known_work_ids,
    render,
    resolve,
    score,
)

__all__ = [
    "AMBIGUOUS",
    "EXIT_AMBIGUOUS",
    "EXIT_OK",
    "EXIT_UNRESOLVED",
    "RESOLVED",
    "UNRESOLVED",
    "Candidate",
    "Resolution",
    "concepts_by_work_id",
    "exact_mentions",
    "known_work_ids",
    "render",
    "resolve",
    "score",
]
