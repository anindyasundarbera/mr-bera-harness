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
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def cmd_guards(args: argparse.Namespace) -> int:
    """Run the pre-session checks. Exit 1 when any guard fails."""
    import json as _json  # noqa: PLC0415 - deferred so --help stays fast

    from harness.guards.session import run_all  # noqa: PLC0415 - deferred so --help stays fast

    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    branch = args.branch or None
    findings = run_all(branch, config, config.root)
    failures = [f for f in findings if not f.ok]

    if args.json:
        print(
            _json.dumps(
                {
                    "passed": not failures,
                    "findings": [
                        {"guard": f.guard, "ok": f.ok, "detail": f.detail} for f in findings
                    ],
                },
                indent=2,
            )
        )
        return 1 if failures else 0

    print("branch guards")
    for finding in findings:
        print(f"  {'PASS' if finding.ok else 'FAIL'}  {finding.guard:<16} {finding.detail}")
    print()
    if failures:
        print(f"GUARDS FAILED ({len(failures)}) — resolve before doing work.")
        print("These guards are advisory: see ADR-2026-002.")
        return 1
    print("All guards passed — session may proceed.")
    return 0


def cmd_commits(args: argparse.Namespace) -> int:
    """Validate commit messages against the configured convention."""
    from harness.entries.commits import (  # noqa: PLC0415 - deferred so --help stays fast
        check,
        commits_in_range,
        default_range,
    )

    if args.message is not None:
        problems = check(args.message)
        for problem in problems:
            print(f"  ! {problem}")
        return 1 if problems else 0

    rev_range = args.rev_range or default_range()
    try:
        commits = commits_in_range(rev_range)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    failed = 0
    print(f"range: {rev_range}  ({len(commits)} commit(s))")
    for sha, subject, body in commits:
        problems = check(subject, body)
        if problems:
            failed += 1
            print(f"  FAIL  {sha[:8]}  {subject}")
            for problem in problems:
                print(f"          {problem}")
        else:
            print(f"  OK    {sha[:8]}  {subject}")

    if failed:
        print(f"\nconvention: FAILED ({failed} of {len(commits)})")
        return 1
    print(f"\nconvention: holds across {len(commits)} commit(s)")
    return 0


def cmd_entries(args: argparse.Namespace) -> int:
    """Validate, or generate, the changelog and ADR indexes."""
    from harness.entries.generator import (  # noqa: PLC0415 - deferred so --help stays fast
        generate,
        validate_all,
    )

    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    changelog, decisions = config.path("changelog"), config.path("decisions")

    if args.entries_command == "generate":
        code, messages = generate(
            check=args.check,
            changelog_dir=changelog,
            decisions_dir=decisions,
        )
        for message in messages:
            print(message)
        return code

    result = validate_all(changelog, decisions)
    print(f"entries: {len(result.entries)}")
    for entry in result.entries:
        print(f"  - {entry.id}  [{entry.kind}]  {entry.date}  {entry.title}")
    print(f"problems: {len(result.problems)}")
    for problem in result.problems:
        print(f"  ! {problem}")
    return 0 if result.ok else 1


def cmd_ci(args: argparse.Namespace) -> int:
    """Rehearse the project's pipeline, and check parity against its CI."""
    from harness.ci.rehearse import (  # noqa: PLC0415 - deferred so --help stays fast
        check_parity,
        default_pipeline,
        run_stage,
    )

    pipeline = default_pipeline()
    root = _config(args).root
    failures: list[str] = []
    for stage in pipeline.stages:
        passed, messages = run_stage(stage, root)
        print(f"[{stage.name}] {stage.description}")
        for message in messages:
            print(message)
        if not passed:
            failures.append(stage.name)
        print()

    workflow = args.workflow
    if workflow:
        ok, messages = check_parity(Path(workflow), root)
        print(f"[parity] local stages vs {workflow}")
        for message in messages:
            print(f"  {message}")
        print()
        if not ok:
            failures.append("parity")

    if failures:
        print(f"RESULT: FAILED — {', '.join(failures)}")
        return 1
    print("RESULT: PASSED")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Build, verify or inspect the derived document index.

    The index is *derived*: it is a function of committed git bytes and nothing
    else. `verify` proves that by dropping the tables, rebuilding from git and
    comparing the two models' digests.
    """
    from harness.extract.model import model_digest  # noqa: PLC0415 - deferred so --help stays fast
    from harness.extract.source import (  # noqa: PLC0415 - deferred so --help stays fast
        IndexSourceError,
        model_from_git,
    )
    from harness.index.store import (  # noqa: PLC0415 - deferred so --help stays fast
        IndexUnavailableError,
        connect,
        read_model,
        reset,
        write_model,
    )

    try:
        config = _config(args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    root = config.root
    dsn = args.dsn or os.environ.get("MRB_HARNESS_DSN")
    try:
        conn = connect(dsn)
    except IndexUnavailableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("The index is a derived store; set MRB_HARNESS_DSN or pass --dsn.")
        return 3

    with conn:
        if args.index_command == "status":
            current = read_model(conn)
            print(f"documents : {len(current.documents)}")
            print(f"registry  : {len(current.registry_tables)} table(s)")
            print(f"commit    : {current.commit_sha or '(not built)'}")
            print(f"digest    : {model_digest(current)}")
            return 0

        try:
            model = model_from_git(root, config, rev=args.rev)
        except IndexSourceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        if args.index_command == "build":
            reset(conn)
            write_model(conn, model)
            print(
                f"indexed {len(model.documents)} document(s) from {model.commit_sha[:12]}"
                f" ({len(model.registry_tables)} registry table(s))"
            )
            print(f"digest: {model_digest(model)}")
            return 0

        # verify: build from git, read back, drop, rebuild from git, compare.
        reset(conn)
        write_model(conn, model)
        first = model_digest(read_model(conn))
        reset(conn)
        write_model(conn, model)
        second = model_digest(read_model(conn))
        if first != second:
            print(f"FAIL rebuild differs: {first} != {second}")
            return 1
        print(f"OK   index rebuilds identically from git: {first}")
        return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Look up documents, links and blockers in the derived index.

    A query answers with code, so the question never reaches a model — which is
    the token saving the architecture is built on. Exit code 3 means the derived
    store is unreachable, matching `harness index`.
    """
    from harness.index.store import (  # noqa: PLC0415 - deferred so --help stays fast
        IndexUnavailableError,
        connect,
    )
    from harness.query import engine  # noqa: PLC0415 - deferred so --help stays fast

    # Validate usage before reaching for a database: an argument error is a
    # usage error whether or not a DSN happens to be reachable.
    if args.query_command == "touching" and args.field not in engine.SCOPE_FIELDS:
        print(
            f"ERROR: field must be one of {', '.join(engine.SCOPE_FIELDS)}, not {args.field!r}",
            file=sys.stderr,
        )
        return 2

    dsn = args.dsn or os.environ.get("MRB_HARNESS_DSN")
    try:
        conn = connect(dsn)
    except IndexUnavailableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Queries read the derived index; set MRB_HARNESS_DSN or pass --dsn.")
        return 3

    command = args.query_command
    try:
        with conn:
            if command == "documents":
                doc_rows = engine.documents(
                    conn, doc_type=args.type, status=args.status, limit=args.limit
                )
                _emit(args, [r.as_dict() for r in doc_rows], _print_rows)
            elif command == "show":
                row = engine.show(conn, args.concept_id)
                if row is None:
                    print(f"not found: {args.concept_id}", file=sys.stderr)
                    return 1
                _emit(args, row.as_dict(), _print_row)
            elif command == "search":
                found_rows = engine.search(conn, args.text, limit=args.limit)
                _emit(args, [r.as_dict() for r in found_rows], _print_rows)
            elif command == "links":
                targets = engine.links(conn, args.concept_id, direction=args.direction)
                _emit(args, targets, _print_lines)
            elif command == "touching":
                touch_rows = engine.touching(conn, args.work_id, field_name=args.field)
                _emit(args, [r.as_dict() for r in touch_rows], _print_rows)
            elif command == "blocked":
                stops = engine.blocked(conn, args.work_id)
                _emit(args, [s.as_dict() for s in stops], _print_blocked)
            elif command == "stops":
                stop_rows = engine.stops(conn, state=args.state)
                _emit(args, stop_rows, _print_stops)
            elif command == "decisions":
                decision_rows = engine.decisions(conn, status=args.status)
                _emit(args, [r.as_dict() for r in decision_rows], _print_rows)
            elif command == "gaps":
                gap_rows = engine.gaps(conn, state=args.state)
                _emit(args, gap_rows, _print_gaps)
            else:  # pragma: no cover - argparse enforces the choice
                print(f"ERROR: unknown query {command!r}", file=sys.stderr)
                return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


def _emit(args: argparse.Namespace, payload: object, printer: Callable[[Any], None]) -> None:
    """Print as JSON when asked, otherwise through the text printer."""
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        printer(payload)


def _print_row(row: dict[str, Any]) -> None:
    print(f"{row['concept_id']}  [{row['doc_type']}]  {row['title']}")
    print(f"  path: {row['path']}")


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(none)")
        return
    for row in rows:
        _print_row(row)


def _print_blocked(stops: list[dict[str, Any]]) -> None:
    if not stops:
        print("no stop conditions apply")
        return
    for stop in stops:
        print(f"STOP  {stop['title']}  [{stop['state']}]  blocker={stop['blocker']}")
        if stop["if_you_guess"]:
            print(f"      if you guess: {stop['if_you_guess']}")
        for rule in stop["must_not_do"]:
            print(f"      must not: {rule}")


def _print_stops(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("no stop conditions")
        return
    for row in rows:
        print(f"{row['work_item']:<20} {row['blocker']:<20} {row['state']:<14} {row['title']}")


def _print_gaps(rows: list[dict[str, str]]) -> None:
    if not rows:
        print("(none)")
        return
    for row in rows:
        identifier = row.get("Gap ID", "?")
        print(f"{identifier}  {row}")


def _print_lines(values: list[str]) -> None:
    if not values:
        print("(none)")
        return
    for value in values:
        print(value)


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

    p = sub.add_parser("guards", help="run the pre-session checks")
    p.add_argument("--branch", help="check as if on this branch")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_guards)

    p = sub.add_parser("commits", help="validate commit messages")
    p.add_argument("rev_range", nargs="?", help="git range, e.g. main..HEAD")
    p.add_argument("--message", help="check a single message and exit")
    p.set_defaults(func=cmd_commits)

    p = sub.add_parser("entries", help="validate or generate changelog/ADR indexes")
    entries_sub = p.add_subparsers(dest="entries_command", required=True)
    entries_sub.add_parser("validate", help="validate entry schema and uniqueness")
    gen = entries_sub.add_parser("generate", help="write the generated index files")
    gen.add_argument("--check", action="store_true", help="fail if regeneration would differ")
    p.set_defaults(func=cmd_entries)

    p = sub.add_parser("ci", help="rehearse the project's pipeline locally")
    p.add_argument("--workflow", help="path to a CI workflow, for the parity check")
    p.set_defaults(func=cmd_ci)

    p = sub.add_parser("index", help="build, verify or inspect the derived document index")
    index_sub = p.add_subparsers(dest="index_command", required=True)
    build = index_sub.add_parser("build", help="load the document model into PostgreSQL")
    build.add_argument("--rev", default="HEAD", help="git revision to index (default: HEAD)")
    build.add_argument("--dsn", help="PostgreSQL DSN (default: $MRB_HARNESS_DSN)")
    verify = index_sub.add_parser("verify", help="prove the index rebuilds identically from git")
    verify.add_argument("--rev", default="HEAD", help="git revision to verify (default: HEAD)")
    verify.add_argument("--dsn", help="PostgreSQL DSN (default: $MRB_HARNESS_DSN)")
    status = index_sub.add_parser("status", help="show the current index's identity")
    status.add_argument("--dsn", help="PostgreSQL DSN (default: $MRB_HARNESS_DSN)")
    p.set_defaults(func=cmd_index)

    # `--dsn` and `--json` are attached to each query subcommand rather than to
    # the `query` parser: argparse does not let a subparser inherit its parent's
    # options, so `harness query documents --json` — the form a user will type —
    # would otherwise fail.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dsn", help="PostgreSQL DSN (default: $MRB_HARNESS_DSN)")
    common.add_argument("--json", action="store_true", help="emit JSON instead of text")

    p = sub.add_parser("query", help="look up documents, links and blockers in the index")
    query_sub = p.add_subparsers(dest="query_command", required=True)

    docs = query_sub.add_parser("documents", parents=[common], help="list documents")
    docs.add_argument("--type", help="filter by concept type")
    docs.add_argument("--status", help="filter by status")
    docs.add_argument("--limit", type=int, help="at most this many")

    one = query_sub.add_parser("show", parents=[common], help="one document by id or path")
    one.add_argument("concept_id")

    find = query_sub.add_parser("search", parents=[common], help="documents mentioning text")
    find.add_argument("text")
    find.add_argument("--limit", type=int, default=50)

    lnk = query_sub.add_parser(
        "links", parents=[common], help="documents linked from, or to, one document"
    )
    lnk.add_argument("concept_id")
    lnk.add_argument("--direction", choices=["in", "out"], default="out")

    touch = query_sub.add_parser(
        "touching", parents=[common], help="documents whose field names a work item"
    )
    touch.add_argument("work_id")
    touch.add_argument("--field", default="covers", help="one of: covers depends_on blocks tags")

    block = query_sub.add_parser(
        "blocked", parents=[common], help="stop conditions that apply to a work item"
    )
    block.add_argument("work_id")

    stops_cmd = query_sub.add_parser(
        "stops", parents=[common], help="every stop condition and what it blocks"
    )
    stops_cmd.add_argument("--state", help="filter by blocker state, e.g. BlockedOwner")

    dec = query_sub.add_parser("decisions", parents=[common], help="decision records")
    dec.add_argument("--status", help="filter by decision status")

    gap = query_sub.add_parser("gaps", parents=[common], help="rows from a gap register")
    gap.add_argument("--state", help="filter by gap state")

    p.set_defaults(func=cmd_query)

    p = sub.add_parser("doctor", help="end-to-end health summary")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
