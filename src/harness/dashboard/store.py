"""Persist usage reports as one file per run.

The same pattern as `ADR-2026-001`'s changelog entries, for the same reason: a
run record is written once and never edited. One file per run means two runs can
never conflict, history accumulates instead of being overwritten, and the newest
run is just the file with the greatest name.

Filenames sort chronologically, because they start with an ISO-8601 timestamp
with a fixed-width UTC offset, so `sorted(glob(...))[-1]` is the latest run
without reading any of them.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DIRNAME = "usage"

#: A fixed-width, lexicographically sortable timestamp. `+00:00` is constant
#: because every run is recorded in UTC, so no filename can sort wrongly.
_STAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


class ReportError(Exception):
    """Raised when a run file is missing or malformed."""


def reports_dir(root: Path, dirname: str = DEFAULT_DIRNAME) -> Path:
    """Where run files live for a repository, under `.harness/`.

    Deliberately not inside the bundle: a run record is telemetry, not knowledge,
    and writing it into `knowledge/` would make the index treat it as a concept.
    """
    return root / ".harness" / dirname


def _stamp(moment: _dt.datetime | None = None) -> str:
    moment = moment or _dt.datetime.now(_dt.timezone.utc)
    return moment.astimezone(_dt.timezone.utc).strftime(_STAMP_FORMAT)


def write_run(
    root: Path,
    payload: dict[str, Any],
    *,
    moment: _dt.datetime | None = None,
    dirname: str = DEFAULT_DIRNAME,
) -> Path:
    """Write one run file. Returns its path.

    Never overwrites: the filename includes the full timestamp to the second, and
    a collision is resolved by appending a counter rather than replacing — losing
    a run record to a same-second write would destroy history silently.
    """
    directory = reports_dir(root, dirname)
    directory.mkdir(parents=True, exist_ok=True)

    base = _stamp(moment)
    target = directory / f"{base}.json"
    counter = 1
    while target.exists():
        target = directory / f"{base}-{counter:02d}.json"
        counter += 1

    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def list_runs(root: Path, dirname: str = DEFAULT_DIRNAME) -> list[Path]:
    """Every run file, oldest first."""
    directory = reports_dir(root, dirname)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def latest_run(root: Path, dirname: str = DEFAULT_DIRNAME) -> Path | None:
    """The most recent run file, or None when nothing has been recorded."""
    runs = list_runs(root, dirname)
    return runs[-1] if runs else None


@dataclass(frozen=True)
class History:
    """The accumulated runs, newest first."""

    runs: tuple[dict[str, Any], ...] = ()

    def __len__(self) -> int:
        return len(self.runs)

    @property
    def latest(self) -> dict[str, Any] | None:
        return self.runs[0] if self.runs else None

    def transitions(self) -> list[dict[str, Any]]:
        """Where a check changed status between consecutive runs.

        The reason to keep history at all: a check that was passing and is now
        failing is the interesting event, and it is invisible in a single run.
        """
        changes: list[dict[str, Any]] = []
        # Oldest to newest, so each transition reads forward in time.
        ordered = list(reversed(self.runs))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            before = {c["name"]: c["status"] for c in previous.get("checks", [])}
            for check in current.get("checks", []):
                old = before.get(check["name"])
                if old is not None and old != check["status"]:
                    changes.append(
                        {
                            "check": check["name"],
                            "from": old,
                            "to": check["status"],
                            "at": current.get("generated_at", ""),
                        }
                    )
        return changes


def load_history(root: Path, dirname: str = DEFAULT_DIRNAME) -> History:
    """Load every run, newest first. A malformed file is reported, not skipped.

    Silently dropping an unreadable run would make history look shorter than it
    is, and a missing entry is indistinguishable from a run that never happened.
    """
    runs: list[dict[str, Any]] = []
    for path in list_runs(root, dirname):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            raise ReportError(f"{path.name} is unreadable: {exc}") from exc
    runs.reverse()  # newest first
    return History(runs=tuple(runs))
