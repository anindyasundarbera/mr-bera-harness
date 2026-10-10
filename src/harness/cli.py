#!/usr/bin/env python3
"""Unified command line for the MrBera session harness.

A consuming repository installs the package and runs `harness <command>` from its
own root. Every command reads `harness.toml`; none of them hardcode a location.

    harness describe              show the resolved configuration
    harness context <WORK-ID>     resolve the documents that bind a work item
    harness conform               check OKF v0.2 conformance of the bundle
    harness routing               validate routing invariants
    harness entries <sub>         validate or generate changelog/ADR indexes
    harness guards                run the pre-session checks
    harness commits [RANGE]       check commit messages
    harness ci                    rehearse the project's pipeline locally
    harness doctor                end-to-end health summary

Exit codes are stable so they can be scripted against:
    0 success
    1 a check failed
    2 usage or configuration error
    3 a stop condition applies (from `context`)
    4 nothing covers the chain (from `context`)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness import __version__
from harness.config import Config, ConfigError, describe, load_config
from harness.routing import resolve_context
from harness.routing.resolve import render


def _config(args: argparse.Namespace) -> Config:
    """Load the project configuration, failing loudly when absent."""
    root = Path(args.root) if getattr(args, "root", None) else Path.cwd()
    return load_config(root, required=True)


def cmd_describe(args: argparse.Namespace) -> int:
    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    describe(config)
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    defining = [s for s in (args.defining or "").split(",") if s]
    try:
        resolved = resolve_context(config, args.work_id, defining=defining)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a usage error
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "work_id": resolved.work_id,
                    "chain": resolved.chain,
                    "load": resolved.load,
                    "excluded": resolved.excluded,
                    "stop_conditions": resolved.stop_conditions,
                },
                indent=2,
            )
        )
    else:
        print(render(resolved))
    return resolved.exit_code()


def cmd_conform(args: argparse.Namespace) -> int:
    from harness.okf import Bundle  # noqa: PLC0415 - deferred so --help stays fast

    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    problems = Bundle(config.path("knowledge")).check()
    print(f"conformance problems: {len(problems)}")
    for problem in problems:
        print(f"  ! {problem}")
    return 1 if problems else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """One command that says whether this project is in a workable state."""
    from harness.entries.generator import validate_all  # noqa: PLC0415 - deferred
    from harness.okf import Bundle  # noqa: PLC0415 - deferred so --help stays fast
    from harness.routing.invariants import validate_routing  # noqa: PLC0415 - deferred

    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    describe(config)
    print()
    failures = 0

    knowledge = config.path("knowledge")
    if not knowledge.is_dir():
        print(f"okf bundle        : {knowledge} does not exist; skipped")
    else:
        bundle = Bundle(knowledge)
        problems = bundle.check()
        print(f"okf concepts      : {len(bundle.concepts())}")
        print(f"okf conformance   : {'clean' if not problems else f'{len(problems)} problem(s)'}")
        for problem in problems:
            print(f"  ! {problem}")
        failures += len(problems)

    report = validate_routing(config)
    print(f"routing invariants: {len(report.violations)} violation(s)")
    for violation in report.violations:
        print(f"  ! {violation}")
    failures += len(report.violations)

    changelog, decisions = config.path("changelog"), config.path("decisions")
    if not (changelog.is_dir() or decisions.is_dir()):
        print("entries           : no changelog or decisions directory; skipped")
    else:
        result = validate_all(changelog, decisions)
        print(
            f"entries           : {len(result.entries)} entr(ies), "
            f"{len(result.problems)} problem(s)"
        )
        for entry_problem in result.problems:
            print(f"  ! {entry_problem}")
        failures += len(result.problems)

    print()
    if failures:
        print(f"DOCTOR: {failures} problem(s)")
        return 1
    print("DOCTOR: clean")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Deterministic context and guard layer for coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"harness {__version__}")
    parser.add_argument("--root", help="project root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("describe", help="show the resolved configuration")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("context", help="resolve documents for a work item")
    p.add_argument("work_id")
    p.add_argument("--defining", help="comma-separated state keys you intend to define")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("conform", help="OKF v0.2 conformance of the bundle")
    p.set_defaults(func=cmd_conform)

    p = sub.add_parser("doctor", help="end-to-end health summary")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
