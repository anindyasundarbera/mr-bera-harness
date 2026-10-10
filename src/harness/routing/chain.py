"""Identifier grammar and parent-chain walking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from harness.okf import OkfError

if TYPE_CHECKING:
    from harness.config import Identity


@dataclass(frozen=True)
class WorkId:
    """A parsed work identifier, split into its levels."""

    raw: str
    prefix: str
    segments: tuple[str, ...]

    @property
    def depth(self) -> int:
        return len(self.segments)


def parse_work_id(work_id: str, identity: Identity | None = None) -> WorkId:
    """Validate and split an identifier against the configured grammar.

    Enforcing the whole grammar rather than a prefix check is deliberate: a lax
    check lets `MRB-X` or `MRB-M06-S7` through, and the malformed identifier then
    silently routes to a coarser parent chain instead of failing.
    """
    from harness.config import Identity as _Identity  # noqa: PLC0415 - avoids a cycle

    identity = identity or _Identity()
    raw = work_id.strip()
    if not identity.id_pattern().match(raw):
        raise OkfError(
            f"not a valid {identity.name} work identifier: {raw!r} "
            f"(expected {identity.id_pattern().pattern})"
        )

    # Each level is a single token: MRB-M06-S07-C03-W01-A02 has one token per
    # level after the prefix. Grouping tokens in pairs (the earlier mistake)
    # produced bogus segments such as "M06-S07" and truncated the parent chain.
    parts = raw.split("-")
    prefix = parts[0]
    segments = tuple(parts[1:])
    expected = len(identity.levels)
    if len(segments) > expected:
        raise OkfError(
            f"{raw!r} has {len(segments)} levels; the configured grammar allows {expected}"
        )
    return WorkId(raw=raw, prefix=prefix, segments=segments)


def parent_chain(work_id: str, identity: Identity | None = None) -> list[str]:
    """Walk an identifier's parent chain, most specific first.

    `MRB-M06-S07-C03-W01-A02` -> [MRB-M06-S07-C03-W01, MRB-M06-S07-C03,
                                  MRB-M06-S07, MRB-M06]
    """
    parsed = parse_work_id(work_id, identity)
    return [
        "-".join([parsed.prefix, *parsed.segments[:depth]]) for depth in range(parsed.depth, 0, -1)
    ]
