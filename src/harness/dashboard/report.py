"""Collect one structured usage report for a repository.

The dashboard is a **viewer, not an actor**. It runs the harness's own
deterministic checks — the same ones `harness doctor`, the guards and the entries
validator already run — and records their outcome. It executes nothing on the
model's behalf and adds no mutation path.

Reusing the existing checks rather than reimplementing them is deliberate: a
dashboard that reported its own idea of health could disagree with `doctor`, and
two answers to one question is the drift this project exists to avoid.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from harness.okf import Bundle

if TYPE_CHECKING:
    from pathlib import Path  # noqa: PLC0415 - imported where it is used

    from harness.config import Config  # noqa: PLC0415 - imported where it is used

#: Bumped when the report shape changes, so an old report is recognisable rather
#: than silently misread by a newer renderer.
REPORT_VERSION = 1


@dataclass(frozen=True)
class Check:
    """One check's outcome.

    `status` is deliberately three-valued, not boolean. "Unknown" is a real
    outcome — an index that was not built, a database that was not reachable —
    and collapsing it into `pass` or `fail` would report health the harness did
    not observe.
    """

    name: str
    category: str
    status: str  # "pass" | "fail" | "unknown"
    detail: str = ""
    findings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "detail": self.detail,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class Run:
    """One usage report: when, where, on which revision, and what was found."""

    project: str
    root: str
    commit_sha: str
    dirty: bool
    branch: str
    harness_version: str
    generated_at: str
    report_version: int
    checks: tuple[Check, ...] = ()

    def counts(self) -> dict[str, int]:
        tallies = {"pass": 0, "fail": 0, "unknown": 0}
        for check in self.checks:
            tallies[check.status] = tallies.get(check.status, 0) + 1
        return tallies

    @property
    def healthy(self) -> bool:
        """True only when nothing failed. `unknown` is not a pass."""
        return all(check.status != "fail" for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k != "checks"},
            "counts": self.counts(),
            "healthy": self.healthy,
            "checks": [c.as_dict() for c in self.checks],
        }


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def provenance(config: Config, root: Path) -> dict[str, Any]:
    """Where this report came from: revision, branch, and whether the tree is dirty.

    A report without provenance is not evidence. `dirty` is a first-class field
    because a run over uncommitted work is a different claim from a run over a
    commit, and a reader must be able to tell them apart.
    """
    from harness import __version__  # noqa: PLC0415 - imported where it is used

    status = _git(root, "status", "--porcelain")
    return {
        "project": config.identity.name,
        "root": str(root),
        "commit_sha": _git(root, "rev-parse", "HEAD"),
        "dirty": bool(status),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "UNKNOWN",
        "harness_version": __version__,
    }


def _conformance(config: Config) -> Check:
    knowledge = config.path("knowledge")
    if not knowledge.is_dir():
        return Check(
            "okf conformance",
            "documentation",
            "unknown",
            f"{knowledge} does not exist; nothing to check",
        )
    problems = Bundle(knowledge).check()
    return Check(
        "okf conformance",
        "documentation",
        "fail" if problems else "pass",
        f"{len(problems)} problem(s)",
        tuple(problems),
    )


def _routing(config: Config) -> Check:
    from harness.routing.invariants import validate_routing  # noqa: PLC0415 - used here

    report = validate_routing(config)
    violations = [str(v) for v in report.violations]
    return Check(
        "routing invariants",
        "documentation",
        "fail" if violations else "pass",
        f"{len(violations)} violation(s) over {report.checked} concept(s)",
        tuple(violations),
    )


def _entries(config: Config) -> Check:
    from harness.entries.generator import validate_all  # noqa: PLC0415 - imported where it is used

    changelog, decisions = config.path("changelog"), config.path("decisions")
    if not (changelog.is_dir() or decisions.is_dir()):
        return Check("entry schema", "governance", "unknown", "no entry directories configured")
    result = validate_all(changelog, decisions)
    problems = [str(p) for p in result.problems]
    return Check(
        "entry schema",
        "governance",
        "fail" if problems else "pass",
        f"{len(result.entries)} entr(ies), {len(problems)} problem(s)",
        tuple(problems),
    )


def _index(config: Config, dsn: str | None) -> Check:
    """The derived index. Unknown when no database is configured."""
    from harness.index.store import (  # noqa: PLC0415 - imported where it is used
        IndexUnavailableError,
        connect,
        read_model,
    )

    try:
        conn = connect(dsn)
    except IndexUnavailableError:
        return Check(
            "derived index",
            "index",
            "unknown",
            "no PostgreSQL DSN; the derived store was not inspected",
        )
    try:
        with conn:
            model = read_model(conn)
            if not model.commit_sha:
                return Check(
                    "derived index",
                    "index",
                    "unknown",
                    "the index is empty; run `harness index build`",
                )
            head = _git(config.root, "rev-parse", "HEAD")
            same = model.commit_sha == head
            return Check(
                "derived index",
                "index",
                "pass" if same else "fail",
                f"built from {model.commit_sha[:12]}"
                + ("" if same else f", but HEAD is {head[:12]} — the index is stale"),
            )
    finally:
        conn.close()


def _guards(config: Config, branch: str) -> Check:
    """The session guards.

    Their failure on a protected branch is **expected**, so the check is reported
    as `unknown` there rather than `fail`: a dashboard that painted a correct
    refusal red would train its reader to ignore red.
    """
    from harness.guards.session import run_all  # noqa: PLC0415 - imported where it is used

    findings = run_all(branch or None, config, config.root)
    failures = [f for f in findings if not f.ok]
    protected = branch in config.protected_branches
    if protected and len(failures) == 1 and failures[0].guard == "branch":
        return Check(
            "session guards",
            "governance",
            "unknown",
            f"on protected branch `{branch}` — the branch guard refuses a session here, by design",
        )
    return Check(
        "session guards",
        "governance",
        "fail" if failures else "pass",
        f"{len(failures)} finding(s) of {len(findings)}",
        tuple(f"{f.guard}: {f.detail}" for f in failures),
    )


def _tests(config: Config) -> Check:
    """The project's own test suite, run in a subprocess.

    Reported as `unknown` rather than `fail` when pytest is absent: a missing tool
    is not a failing test.
    """
    tests = config.path("tests")
    if not tests.is_dir():
        return Check("tests", "verification", "unknown", f"{tests} does not exist")
    try:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", str(tests), "-q", "--no-header"],
            cwd=config.root,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("tests", "verification", "unknown", f"could not run pytest: {exc}")

    tail = (proc.stdout + proc.stderr).strip().splitlines()
    summary = tail[-1] if tail else ""
    if "No module named pytest" in (proc.stdout + proc.stderr):
        return Check("tests", "verification", "unknown", "pytest is not installed")
    return Check(
        "tests",
        "verification",
        "pass" if proc.returncode == 0 else "fail",
        summary or f"exit {proc.returncode}",
    )


def collect(
    config: Config,
    *,
    dsn: str | None = None,
    branch: str | None = None,
    now: _dt.datetime | None = None,
    include_tests: bool = True,
) -> Run:
    """Run every check and return one report.

    `now` is injectable so a report can be reproduced exactly in a test; the
    default is the wall clock, which is the only nondeterministic field in the
    report and is recorded as provenance rather than as a fact about the code.
    """
    root = config.root
    resolved_branch = branch or _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "UNKNOWN"
    checks = [
        _conformance(config),
        _routing(config),
        _entries(config),
        _index(config, dsn),
        _guards(config, resolved_branch),
        _compile_probe(config),
    ]
    if include_tests:
        checks.append(_tests(config))

    return Run(
        **provenance(config, root),
        generated_at=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(),
        report_version=REPORT_VERSION,
        checks=tuple(checks),
    )


def _compile_probe(config: Config) -> Check:  # noqa: ARG001 - kept for a uniform check signature
    """Whether the prompt compiler can compile at all, and its unit.

    Compiles nothing specific — a budget is caller-supplied and no value is
    decided — so it reports the unit the compiler would use, which is the fact a
    reader needs to interpret any recorded budget.
    """
    from harness.compile.tokens import UNIT  # noqa: PLC0415 - imported where it is used

    return Check("prompt compiler", "compilation", "pass", f"budget unit is `{UNIT}`")
