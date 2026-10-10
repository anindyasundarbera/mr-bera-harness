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

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent

# Branches a coding agent may work on. `main` is deliberately excluded.
# Defaults; a project overrides these through `harness.toml`. The defaults exist
# so the guard functions remain usable without a config, which keeps the module
# testable in isolation.
DEFAULT_BRANCH_PREFIXES = (
    "feat",
    "fix",
    "docs",
    "chore",
    "refactor",
    "test",
    "ci",
    "integration",
)
PROTECTED_BRANCHES = ("main", "master")


def _patterns(prefixes: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile one branch pattern per configured prefix.

    Patterns are anchored, so `evil-feat/x` cannot match `feat`. An unanchored
    pattern would silently allow a branch that merely contains the prefix.
    """
    return tuple(re.compile(rf"^{re.escape(p)}/[a-z0-9._-]+$") for p in prefixes)


def _branch_rules(config: Config | None) -> tuple[tuple[re.Pattern[str], ...], tuple[str, ...]]:
    if config is None:
        return _patterns(DEFAULT_BRANCH_PREFIXES), PROTECTED_BRANCHES
    return _patterns(config.branch_prefixes), config.protected_branches


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


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run git in the project root, or an explicit directory.

    `cwd` is explicit rather than implicit so a caller (or a test) can point the
    helpers at a different repository without mutating module state.
    """
    return subprocess.run(  # noqa: S603
        ["git", *args], cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=False
    )


def current_branch(root: Path | None = None) -> str:
    proc = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    return proc.stdout.strip() or "UNKNOWN"


def default_branch(root: Path | None = None) -> str:
    proc = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=root)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().split("/")[-1]
    return "main"


def guard_branch(branch: str, config: Config | None = None) -> Finding:
    patterns, protected = _branch_rules(config)
    if branch in protected:
        return Finding(
            "branch",
            False,
            f"on protected branch `{branch}`. Create a feature branch: `git switch -c feat/<slug>`",
        )
    if branch == "HEAD":
        return Finding("branch", False, "detached HEAD; check out a named branch")
    if not any(p.match(branch) for p in patterns):
        prefixes = config.branch_prefixes if config else DEFAULT_BRANCH_PREFIXES
        allowed = " ".join(f"{p}/" for p in prefixes)
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


def guard_secrets_untracked(config: Config | None = None) -> Finding:
    """Refuse to start if a secret is tracked. `.gitignore` cannot fix this."""
    patterns = (
        tuple(re.compile(g) for g in config.forbidden_path_globs)
        if config is not None
        else FORBIDDEN_TRACKED_PATTERNS
    )
    proc = git("ls-files")
    offenders = [path for path in proc.stdout.splitlines() if any(p.search(path) for p in patterns)]
    if offenders:
        return Finding(
            "secrets",
            False,
            f"{len(offenders)} forbidden path(s) tracked: {', '.join(offenders[:5])}. "
            "Run `git rm --cached <path>`; rotation is a separate owner action.",
        )
    return Finding("secrets", True, "no secret or runtime-state paths tracked")


def guard_index_clean_of_secrets(config: Config | None = None) -> Finding:
    """Refuse to start if a secret is staged for the next commit."""
    patterns = (
        tuple(re.compile(g) for g in config.forbidden_path_globs)
        if config is not None
        else FORBIDDEN_TRACKED_PATTERNS
    )
    proc = git("diff", "--cached", "--name-only")
    offenders = [p for p in proc.stdout.splitlines() if any(pat.search(p) for pat in patterns)]
    if offenders:
        return Finding("staged-secrets", False, f"staged for commit: {', '.join(offenders[:5])}")
    return Finding("staged-secrets", True, "nothing forbidden staged")


def guard_status_clean_of_markers(root: Path | None = None) -> Finding:
    """A conflict marker in a tracked file means a merge was left half-resolved."""
    proc = git("ls-files", "*.py", "*.md", "*.yml", "*.yaml", "*.toml")
    base = root or REPO_ROOT
    hits: list[str] = []
    for rel in proc.stdout.splitlines()[:400]:
        path = base / rel
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


def guard_invariants(config: Config | None = None, root: Path | None = None) -> Finding:
    """Run the routing and entry invariants in-process.

    Earlier this shelled out to a project's own `tools/*.py` scripts, which
    coupled the guard to one repository's layout. Calling the harness's own
    validators keeps it working for any consumer.
    """
    import contextlib  # noqa: PLC0415 - deferred to avoid an import cycle
    import io  # noqa: PLC0415 - deferred to avoid an import cycle

    from harness.config import load_config  # noqa: PLC0415 - deferred
    from harness.entries.generator import validate_all  # noqa: PLC0415 - deferred
    from harness.routing.invariants import validate_routing  # noqa: PLC0415 - deferred

    base = root or (config.root if config else REPO_ROOT)
    failures: list[str] = []

    try:
        config = config or load_config(base)
    except Exception as exc:  # noqa: BLE001 - reported as a guard failure
        return Finding("invariants", False, f"configuration is unusable: {exc}")

    if config.path("knowledge").is_dir():
        with contextlib.redirect_stdout(io.StringIO()):
            report = validate_routing(config)
        if report.violations:
            failures.append(f"routing ({len(report.violations)})")

    changelog, decisions = config.path("changelog"), config.path("decisions")
    if changelog.is_dir() or decisions.is_dir():
        with contextlib.redirect_stdout(io.StringIO()):
            entries = validate_all(changelog, decisions)
        if entries.problems:
            failures.append(f"entries ({len(entries.problems)})")

    if failures:
        return Finding("invariants", False, f"failed: {', '.join(failures)}")
    return Finding("invariants", True, "routing and entry invariants hold")


def guard_base_branch_is_default(
    branch: str | None = None, config: Config | None = None
) -> Finding:
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
    _, protected = _branch_rules(config)
    if branch in protected or branch == "HEAD":
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


def run_all(
    branch: str | None = None, config: Config | None = None, root: Path | None = None
) -> list[Finding]:
    """Run every guard. `branch` defaults to the checked-out branch."""
    branch = branch or current_branch()
    return [
        guard_branch(branch, config),
        guard_base_branch_is_default(branch, config),
        guard_no_untracked_conflicts(),
        guard_secrets_untracked(config),
        guard_index_clean_of_secrets(config),
        guard_status_clean_of_markers(root),
        guard_invariants(config, root),
    ]
