"""Count the unit a prompt budget is expressed in.

A model's tokenizer is a dependency on the *provider*, and the budget would then
mean something different per provider. An exact, deterministic count is the right
unit for a compiler whose whole value is reproducibility: it depends on nothing
but the text.

The unit is named explicitly (`UNIT`) and exposed, because a count that does not
state its unit is not a measurement. It is a **word** count, which correlates with
a model's tokens but does not equal them.

**The tokenizer is a `DecisionRequired`.** If a budget must be expressed in a
specific model's tokens, the counting method has to become a recorded decision
rather than an assumption, and every fingerprint recorded under the old unit
becomes incomparable. `ADR-2026-010` records this.
"""

from __future__ import annotations

import re

#: The unit `count_units` returns. Named so a caller can never mistake it for a
#: model's tokens, which it is not.
UNIT = "word"

#: Runs of non-whitespace. Chosen over `str.split()` so the count is explicit
#: about what it measures rather than inheriting a method's incidental behaviour.
_WORD_RE = re.compile(r"\S+")


def count_units(text: str) -> int:
    """Count words in `text`, deterministically.

    The same bytes always give the same number; nothing here reads a clock, a
    locale or the filesystem.
    """
    return len(_WORD_RE.findall(text))


def count_units_by_line(text: str) -> list[int]:
    """Per-line counts, so a caller can attribute a budget to a section."""
    return [count_units(line) for line in text.splitlines()]
