#!/usr/bin/env python3
"""Refresh the mechanical facts in the live handoff document.

The handoff (`docs/design/REMAINING_WORK.md`) is a narrative document that also
carries a handful of facts a machine knows exactly — how many concepts, entries, test
modules and declarations the repository holds. Those were refreshed **by hand** in the
session that wrote v2.0, and by-hand facts are the thing this repository keeps finding
decayed: `CHG-2026-016` fixed a hardcoded source path, and `CHG-2026-020` fixed the
README still claiming a gap that had closed. This script exists so the mechanical part
cannot decay the same way.

## What it does

It **derives** every fact from the repository through the harness's own library —
the OKF `Bundle`, the entries `validate_all`, the provenance `check`, the resolved
`Config` — rather than re-implementing any of them. A second implementation would be a
second definition of "the entry count", and the two would drift.

It rewrites **only** the region between the two markers in the handoff:

    <!-- harness:handoff-facts:start -->
    ...generated table...
    <!-- harness:handoff-facts:end -->

Everything outside those markers is hand-written and untouched. The markers are
required: a script that rewrote a document without them would have to guess which prose
was generated, and guessing here means deleting someone's paragraph.

## What is deliberately not derived, and why

Two categories are left out, and each exclusion has a failure attached:

- **The revision and whether the tree is dirty.** These describe *the checkout*, not
  the repository. A committed file cannot contain its own commit's hash, so a region
  stating `Revision: <HEAD>` is **stale the moment it is committed** — `--check` could
  never return `0`, and the scheduled job would rewrite the same lines forever. A
  handoff that names a revision has to hand-write it, which is honest because it is
  then a claim a person made and can be seen to have made.
- **The test pass and skip counts.** They are a property of the *environment*, not the
  repository: the same commit reports `606 passed, 77 skipped` without a database and a
  different pair with one. Generating them would make `--check` flap between machines,
  which is the class of defect this repository has already paid for twice (a coverage
  floor measured differently with and without `MRB_TEST_DSN`). Test results belong in
  the changelog entry, with their provenance, which is where they are.

The rule those two exclusions follow, stated once: **the region holds facts that are
functions of the committed content.** A fact about the checkout or about the machine
running the script is not a fact about the repository.

## What it cannot do

It cannot write the narrative — what was built, what is blocked, what the next session
should do. That is a judgement, and a script that generated it would be inventing a
handoff. The scheduled session runs this script **and** edits the prose around it; the
script's job is to make the surrounding prose trustworthy by keeping the facts under it
true.

Exit codes, matching the harness's contract:

    0  the region is current (or was refreshed)
    1  `--check` only: the region is stale
    2  usage, or a handoff without the required markers
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from harness import __version__, load_config
from harness.entries.generator import validate_all
from harness.okf import Bundle
from harness.provenance.checks import check

# The invoking repository, never this file's own location. Getting this wrong is the
# defect this repository has fixed five times (`guards/session.py`, `entries/commits.py`,
# `entries/generator.py`, `ci/rehearse.py` twice): a library answering about its own
# context instead of its caller's.
REPO_ROOT = Path.cwd()

HANDOFF = Path("docs/design/REMAINING_WORK.md")

MARKER_START = "<!-- harness:handoff-facts:start -->"
MARKER_END = "<!-- harness:handoff-facts:end -->"

_MARKER_RE = re.compile(
    re.escape(MARKER_START) + r"\n(?P<body>.*?)" + re.escape(MARKER_END),
    re.DOTALL,
)


@dataclass(frozen=True)
class Facts:
    """The mechanical facts a handoff states, derived — never asserted.

    Every field is a function of the committed content: none describes the checkout or
    the machine that ran the script (see the module docstring for why that matters).
    """

    generated_by: str
    concepts: int
    entries: int
    entry_problems: int
    test_modules: int
    declarations: int
    commit_types: int


def collect_facts(root: Path | None = None) -> Facts:
    """Derive every fact from the repository through the harness's own code."""
    root = root or REPO_ROOT
    config = load_config(root)

    entries = validate_all(config.path("changelog"), config.path("decisions"))
    declarations = check(config)

    tests_dir = config.path("tests")
    return Facts(
        generated_by=f"mr-bera-harness {__version__}",
        concepts=len(Bundle(config.path("knowledge")).concepts()),
        entries=len(entries.entries),
        entry_problems=len(entries.problems),
        test_modules=len(list(tests_dir.glob("test_*.py"))) if tests_dir.is_dir() else 0,
        declarations=len(declarations.declarations),
        commit_types=len(config.commit_types),
    )


def render_facts(facts: Facts) -> str:
    """Render the generated table. No prose judgement, only derived values."""
    return (
        "| Fact | Value |\n"
        "|---|---|\n"
        f"| Derived by | `{facts.generated_by}`, via `tools/refresh_handoff.py` |\n"
        f"| OKF concepts | {facts.concepts} |\n"
        f"| Entries | {facts.entries} ({facts.entry_problems} problem(s)) |\n"
        f"| Test modules | {facts.test_modules} |\n"
        f"| Provenance declarations | {facts.declarations} |\n"
        f"| Commit types accepted | {facts.commit_types} |\n"
    )


def splice(document: str, body: str) -> str:
    """Replace the marked region's body, leaving every other byte alone.

    Raises `ValueError` when a marker is missing. A silent no-op would report success
    while refreshing nothing, which is worse than refusing: the caller would believe
    the handoff had been refreshed.
    """
    if MARKER_START not in document or MARKER_END not in document:
        raise ValueError(
            f"the handoff has no `{MARKER_START}` / `{MARKER_END}` region. Add the "
            "markers before running this, so it knows which lines it owns and which "
            "are hand-written."
        )
    return _MARKER_RE.sub(lambda _m: f"{MARKER_START}\n{body}{MARKER_END}", document, count=1)


def current_region(document: str) -> str:
    match = _MARKER_RE.search(document)
    return match.group("body") if match else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_handoff.py",
        description="Refresh the mechanical facts in the live handoff document.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the marked region is stale; write nothing",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="project root")
    args = parser.parse_args(argv)

    handoff = args.root / HANDOFF
    if not handoff.is_file():
        print(f"no handoff at {handoff}", file=sys.stderr)
        return 2

    document = handoff.read_text(encoding="utf-8")
    try:
        refreshed = splice(document, render_facts(collect_facts(args.root)))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if refreshed == document:
        print(f"{HANDOFF}: facts current")
        return 0

    if args.check:
        print(
            f"{HANDOFF}: STALE — the marked region differs from the repository. "
            "Re-run without --check to refresh it.",
            file=sys.stderr,
        )
        return 1

    handoff.write_text(refreshed, encoding="utf-8")
    print(f"{HANDOFF}: facts refreshed")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through `main()`
    raise SystemExit(main())
