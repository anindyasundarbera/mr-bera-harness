#!/usr/bin/env python3
"""Validate commit messages against the Conventional Commits 1.0.0 spec.

Enforcing the convention in code rather than in a style guide, for the same
reason as every other check here: a rule an agent must remember is a rule it
will eventually forget.

Spec: https://www.conventionalcommits.org/en/v1.0.0/

Usage
-----
    python3 tools/check_commit_convention.py                  # check the range
    python3 tools/check_commit_convention.py --range A..B     # explicit range
    python3 tools/check_commit_convention.py --message "..."  # check one message

Exit codes: 0 = clean, 1 = violations, 2 = usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The Angular-derived type set, which conventionalcommits.org names explicitly.
TYPES = frozenset(
    {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"}
)

# <type>[(scope)][!]: <description>
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<break>!)?: (?P<desc>.+)$")

MAX_SUBJECT = 100
# Merge commits are generated, not authored, so they are exempt. The patterns are
# deliberately precise: a bare `^Merge ` would also exempt a real commit whose
# description merely starts with the word, which is a false negative.
#
# GitHub Actions additionally checks out a pull request at a synthetic merge
# commit whose subject is `Merge <sha> into <sha>`. The narrower
# "Merge branch|pull request|remote-tracking" form missed that, so the convention
# check failed on every pull request while passing on a direct push — the
# difference being which commit each event checks out.
MERGE_RE = re.compile(
    r"^Merge (?:branch |pull request |remote-tracking |[0-9a-f]{7,40} into [0-9a-f]{7,40})"
)
REVERT_RE = re.compile(r"^Revert ")


def check(subject: str, body: str = "") -> list[str]:
    """Return a list of problems with one commit message. Empty means conformant."""
    problems: list[str] = []

    if MERGE_RE.match(subject) or REVERT_RE.match(subject):
        return []  # generated, not authored

    match = SUBJECT_RE.match(subject)
    if not match:
        return [f"subject does not match `<type>[(scope)][!]: <description>`: {subject!r}"]

    ctype = match.group("type")
    if ctype not in TYPES:
        problems.append(f"unknown type `{ctype}`; expected one of {', '.join(sorted(TYPES))}")

    if len(subject) > MAX_SUBJECT:
        problems.append(f"subject is {len(subject)} chars; keep it under {MAX_SUBJECT}")

    desc = match.group("desc")
    if desc.endswith("."):
        problems.append("description ends with a period; drop it")
    if desc[:1].isupper():
        problems.append("description starts uppercase; use lower case")

    # Per the spec, `!` after the type OR a `BREAKING CHANGE:` footer signals a
    # breaking change. Either alone is conformant, so demanding both would reject
    # valid commits. The footer's content is checked when it is present.
    if "BREAKING CHANGE:" in body:
        marker = body.split("BREAKING CHANGE:", 1)[1].strip()
        if not marker:
            problems.append("`BREAKING CHANGE:` footer is empty; describe the change")

    return problems


def _resolve_range(rev_range: str) -> None:
    """Make the range resolvable if a shallow checkout is missing the base ref.

    `actions/checkout@v4` performs a shallow fetch by default, so the base branch
    often does not exist locally in CI even though it does on a developer's
    machine. That is an environment gap, not a commit-message problem, so it is
    repaired here rather than reported as a violation.
    """
    base = rev_range.split("..", maxsplit=1)[0].strip()
    if not base or "/" not in base:
        return

    exists = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", base],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if exists.returncode == 0:
        return

    remote, _, branch = base.partition("/")
    subprocess.run(  # noqa: S603
        [
            "git",
            "fetch",
            "--no-tags",
            "--quiet",
            remote,
            f"+refs/heads/{branch}:refs/remotes/{base}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_log(rev_range: str) -> subprocess.CompletedProcess[str]:
    sep = "\x1f"
    return subprocess.run(  # noqa: S603
        ["git", "log", f"--format=%H{sep}%s{sep}%b\x1e", rev_range],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def commits_in_range(rev_range: str) -> list[tuple[str, str, str]]:
    """Return (sha, subject, body) for each commit in the range."""
    _resolve_range(rev_range)
    proc = _git_log(rev_range)
    if proc.returncode != 0:
        _resolve_range(rev_range)
        proc = _git_log(rev_range)

    if proc.returncode != 0:
        first = proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "unknown error"
        raise SystemExit(
            f"cannot resolve commit range `{rev_range}`: {first}\n"
            "A shallow checkout may be missing the base ref. Fetch it, or pass "
            "an explicit --range."
        )

    sep = "\x1f"
    commits: list[tuple[str, str, str]] = []
    for raw_record in proc.stdout.split("\x1e"):
        record = raw_record.strip("\n")
        if not record:
            continue
        parts = record.split(sep)
        if len(parts) >= 3:
            commits.append((parts[0], parts[1].strip(), parts[2].strip()))
    return commits


def default_range() -> str:
    """The range to check: this branch's commits not already on the default branch."""
    for candidate in ("origin/main..HEAD", "mr_bera/main..HEAD", "main..HEAD"):
        base = candidate.split("..")[0]
        proc = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--verify", "--quiet", base],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return candidate
    # Fall back to `HEAD`, a single commit, which always resolves however shallow
    # the checkout. A depth-1 clone has no parent, so `HEAD~1..HEAD` is not merely
    # empty but unresolvable, which made this tool exit 2 in CI while passing
    # locally.
    return "HEAD"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check commit messages.")
    parser.add_argument("--range", dest="rev_range", default=None)
    parser.add_argument("--message", default=None, help="check a single message and exit")
    args = parser.parse_args(argv)

    if args.message is not None:
        problems = check(args.message)
        for p in problems:
            print(f"  ! {p}")
        return 1 if problems else 0

    rev_range = args.rev_range or default_range()
    try:
        commits = commits_in_range(rev_range)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not commits:
        print(f"no commits in range {rev_range}")
        return 0

    failed = 0
    print(f"range: {rev_range}  ({len(commits)} commit(s))")
    for sha, subject, body in commits:
        problems = check(subject, body)
        if problems:
            failed += 1
            print(f"  FAIL  {sha[:8]}  {subject}")
            for p in problems:
                print(f"          {p}")
        else:
            print(f"  OK    {sha[:8]}  {subject}")

    if failed:
        print(f"\nconvention: FAILED ({failed} of {len(commits)})")
        return 1
    print(f"\nconvention: holds across {len(commits)} commit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
