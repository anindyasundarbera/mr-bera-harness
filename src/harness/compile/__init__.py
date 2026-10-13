"""Deterministic prompt compilation: a work item in, a bounded prompt out.

Build-order step 3 of `HARNESS_ARCHITECTURE.md` §9. Pure code — no LLM, no clock,
no network — so the same committed revision always compiles the same prompt with
the same fingerprint.
"""

from harness.compile.prompt import (
    EXIT_BLOCKED,
    EXIT_NO_SELECTION,
    EXIT_OK,
    EXIT_OVER_BUDGET,
    EXIT_USAGE,
    LOADED_BUDGETS,
    CompiledPrompt,
    CompileError,
    Entry,
    compile_prompt,
)
from harness.compile.tokens import UNIT, count_units

__all__ = [
    "EXIT_BLOCKED",
    "EXIT_NO_SELECTION",
    "EXIT_OK",
    "EXIT_OVER_BUDGET",
    "EXIT_USAGE",
    "LOADED_BUDGETS",
    "UNIT",
    "CompileError",
    "CompiledPrompt",
    "Entry",
    "compile_prompt",
    "count_units",
]
