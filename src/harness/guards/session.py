#!/usr/bin/env python3
"""Activate the branch guards for a coding-agent session.

Runs **before** a coding agent starts work. Its job is to make the branch rules
visible and to refuse the obvious violations, so a session cannot begin in a
state that violates the branch policy.

What this genuinely enforces, and what it does not
--------------------------------------------------
Enforced locally (a real, immediate failure):

* the working tree is on an allowed branch;
* no secret files are staged or tracked;
* the working tree has no uncommitted conflict markers;
* every routing/entry invariant passes.

**Not enforced:** GitHub cannot block a push to `main` on this plan (see
ADR-2026-002 and docs/DELIVERY_INFRASTRUCTURE.md). These guards are advisory at
the server boundary. `--force` / `git push --no-verify` bypass the local hook.
This script therefore makes the wrong action *loud*, not *impossible*.

Usage
-----
    python3 tools/activate_guards.py                 # check, report, exit
    python3 tools/activate_guards.py --branch B     # check as if on branch B
    python3 tools/activate_guards.py --json          # machine-readable

Exit codes: 0 = session may proceed, 1 = a guard failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Branches a coding agent may work on. `main` is deliberately excluded.
ALLOWED_BRANCH_PATTERNS = (
    re.compile(r"^(feat|fix|docs|chore|refactor|test|ci)/[a-z0-9._-]+$"),
    re.compile(r"^(integration)/[a-z0-9._-]+$"),
)
PROTECTED_BRANCHES = ("main", "master")

# Paths that must never be tracked. `.gitignore` cannot untrack them, so they
# are checked explicitly.
#
# `.env.example` is deliberately NOT matched: a template without values must be
# committable, or nobody can document which keys exist. The negative lookahead
# excludes the documented variants while still catching `.env`, `.env.local` and
# `.env.production`.
FORBIDDEN_TRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env(?!\.example(\.|$))(\.|$)"),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$"),
    re.compile(r"(^|/)(credentials|secrets)\.(json|ya?ml)$"),
    re.compile(r"^\.reasonix/"),
)

CONFLICT_MARKERS = ("<<<<<<<", ">>>>>>>", "=======")


@dataclass
class Finding:
    guard: str
    ok: bool
    detail: str


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def current_branch() -> str:
    proc = git("rev-parse", "--abbrev-ref", "HEAD")
    return proc.stdout.strip() or "UNKNOWN"


def default_branch() -> str:
    proc = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().split("/")[-1]
    return "main"


def guard_branch(branch: str) -> Finding:
    if branch in PROTECTED_BRANCHES:
        return Finding(
            "branch",
            False,
            f"on protected branch `{branch}`. Create a feature branch: `git switch -c feat/<slug>`",
        )
    if branch == "HEAD":
        return Finding("branch", False, "detached HEAD; check out a named branch")
    if not any(p.match(branch) for p in ALLOWED_BRANCH_PATTERNS):
        allowed = "feat/ fix/ docs/ chore/ refactor/ test/ ci/ integration/"
        return Finding("branch", False, f"`{branch}` does not match an allowed prefix ({allowed})")
    return Finding("branch", True, f"`{branch}` is an allowed branch")


def guard_no_untracked_conflicts() -> Finding:
    """Refuse to start on a tree containing unresolved merge conflicts."""
    proc = git("diff", "--name-only", "--diff-filter=U")
    conflicted = [f for f in proc.stdout.split() if f]
    if conflicted:
        return Finding(
            "conflicts",
            False,
            f"{len(conflicted)} unresolved conflict(s): {', '.join(conflicted[:5])}",
        )
    return Finding("conflicts", True, "no unresolved merge conflicts")


def guard_secrets_untracked() -> Finding:
    """Refuse to start if a secret is tracked. `.gitignore` cannot fix this."""
    proc = git("ls-files")
    offenders = [
        path
        for path in proc.stdout.splitlines()
        if any(p.search(path) for p in FORBIDDEN_TRACKED_PATTERNS)
    ]
    if offenders:
        return Finding(
            "secrets",
            False,
            f"{len(offenders)} forbidden path(s) tracked: {', '.join(offenders[:5])}. "
            "Run `git rm --cached <path>`; rotation is a separate owner action.",
        )
    return Finding("secrets", True, "no secret or runtime-state paths tracked")


def guard_index_clean_of_secrets() -> Finding:
    """Refuse to start if a secret is staged for the next commit."""
    proc = git("diff", "--cached", "--name-only")
    staged = proc.stdout.splitlines()
    offenders = [p for p in staged if any(pat.search(p) for pat in FORBIDDEN_TRACKED_PATTERNS)]
    if offenders:
        return Finding("staged-secrets", False, f"staged for commit: {', '.join(offenders[:5])}")
    return Finding("staged-secrets", True, "nothing forbidden staged")


def guard_status_clean_of_markers() -> Finding:
    """A conflict marker in a tracked file means a merge was left half-resolved."""
    proc = git("ls-files", "*.py", "*.md", "*.yml", "*.yaml", "*.toml")
    hits: list[str] = []
    for rel in proc.stdout.splitlines()[:400]:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(CONFLICT_MARKERS):
                    hits.append(rel)
                    break
        except OSError:
            continue
    if hits:
        return Finding("markers", False, f"conflict markers found in: {', '.join(hits[:5])}")
    return Finding("markers", True, "no conflict markers in tracked sources")


def guard_invariants() -> Finding:
    """Run the routing and entry invariants; this is the real gate."""
    failures: list[str] = []
    checks = [
        (
            "routing invariants",
            [sys.executable, "tools/validate_routing.py", "knowledge", "--quiet"],
        ),
        ("entry schema", [sys.executable, "tools/entries.py", "validate"]),
        ("resolver contract", [sys.executable, "tools/check_resolver_contract.py"]),
    ]
    for label, argv in checks:
        proc = subprocess.run(  # noqa: S603
            argv, cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            failures.append(label)
    if failures:
        return Finding("invariants", False, f"failed: {', '.join(failures)}")
    return Finding("invariants", True, "routing, entries and resolver contract all pass")


def guard_base_branch_is_default(branch: str | None = None) -> Finding:
    """Refuse a feature branch whose base is another feature branch.

    This is the guard that would have prevented a five-branch stack from being
    created. Trunk-Based Development warns specifically against long-lived
    branches; a branch based on another feature branch inherits that branch's
    lifetime and cannot merge until its ancestor does, which is the definition
    of the problem.

    Evidence level: this guard exists because stacking was tried and collapsed
    a pull request when its base branch moved.
    """
    branch = branch or current_branch()
    if branch in PROTECTED_BRANCHES or branch == "HEAD":
        return Finding("base-branch", True, "not a feature branch")

    default = default_branch()
    # The merge-base with the default branch tells us where this branch really
    # forked from, independent of any intermediate branch name.
    proc = git("rev-parse", f"refs/remotes/origin/{default}")
    if proc.returncode != 0:
        proc = git("rev-parse", default)
    if proc.returncode != 0:
        return Finding("base-branch", True, "default branch not resolvable; skipped")

    merge_base = git("merge-base", "HEAD", f"refs/remotes/origin/{default}")
    if merge_base.returncode != 0:
        merge_base = git("merge-base", "HEAD", default)
    if merge_base.returncode != 0:
        return Finding("base-branch", True, "merge-base not resolvable; skipped")

    tip = git("rev-parse", f"refs/remotes/origin/{default}")
    if tip.returncode != 0:
        tip = git("rev-parse", default)
    if tip.returncode != 0:
        return Finding("base-branch", True, "default branch tip not resolvable; skipped")

    if merge_base.stdout.strip() != tip.stdout.strip():
        return Finding(
            "base-branch",
            False,
            f"`{branch}` is not based on the tip of `{default}`. Rebase onto "
            f"`{default}` before opening a pull request, or you are stacking "
            "branches (see ADR-2026-006).",
        )
    return Finding("base-branch", True, f"`{branch}` is based on `{default}`")


def run_all(branch: str) -> list[Finding]:
    return [
        guard_branch(branch),
        guard_base_branch_is_default(branch),
        guard_no_untracked_conflicts(),
        guard_secrets_untracked(),
        guard_index_clean_of_secrets(),
        guard_status_clean_of_markers(),
        guard_invariants(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate branch guards for a session.")
    parser.add_argument("--branch", default=None, help="check as if on this branch")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    branch = args.branch or current_branch()
    findings = run_all(branch)
    failures = [f for f in findings if not f.ok]

    if args.json:
        print(
            json.dumps(
                {
                    "branch": branch,
                    "default_branch": default_branch(),
                    "passed": not failures,
                    "findings": [
                        {"guard": f.guard, "ok": f.ok, "detail": f.detail} for f in findings
                    ],
                },
                indent=2,
            )
        )
        return 0 if not failures else 1

    print("MrBera branch guards")
    print(f"  branch: {branch}")
    print(f"  default: {default_branch()} (protected; never commit or push directly)")
    print("")
    for finding in findings:
        print(f"  {'PASS' if finding.ok else 'FAIL'}  {finding.guard:<16} {finding.detail}")
    print("")

    if failures:
        print(f"GUARDS FAILED ({len(failures)}) — resolve before doing work.")
        print("")
        print("Reminder: these guards are advisory. GitHub cannot enforce branch")
        print("protection on this plan (ADR-2026-002), so a push to main is")
        print("possible even when this script fails. Do not rely on it as a wall.")
        return 1

    print("All guards passed — session may proceed.")
    print("")
    print("Rules that remain in force for this session:")
    print("  - never commit or push directly to the default branch")
    print("  - one logical change per branch; open a PR for review")
    print("  - a human reviews and merges; no agent self-approval")
    print("  - run `python3 tools/local_ci.py` before pushing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
