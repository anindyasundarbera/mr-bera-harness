"""The check itself: verify each declaration against the decision it names.

Split from `links.py` only so the parsing rules and the verdict stay readable; both
are one concern — a link that is not checked is a comment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness.provenance.links import (
    DIGEST_PREFIX_LENGTH,
    Declaration,
    Report,
    load_decisions,
    scan,
)

if TYPE_CHECKING:
    from harness.config import Config


def check(
    config: Config,
    *,
    sources: list[str] | None = None,
    require_every_file_linked: bool = False,
) -> Report:
    """Verify every declaration, and optionally report unlinked source files."""

    root = config.root
    report = Report()
    report.decisions = load_decisions(config.path("decisions"))
    report.declarations = scan(root, sources=sources)

    for declaration in report.declarations:
        decision = report.decisions.get(declaration.decision_id)
        if decision is None:
            report.broken.append(
                (
                    declaration,
                    f"no decision record `{declaration.decision_id}` in {config.paths.decisions}/",
                )
            )
            continue
        expected = decision.anchor_digest[:DIGEST_PREFIX_LENGTH]
        if declaration.digest != expected:
            report.stale.append(
                (
                    declaration,
                    f"`{decision.decision_id}` has changed since this file declared it "
                    f"(declared sha256:{declaration.digest}, now sha256:{expected}) — "
                    "re-read the decision and either update the declaration or revert "
                    "the change",
                )
            )

    if require_every_file_linked:
        declared = {d.path for d in report.declarations}
        for base in sources or ["src"]:
            directory = root / base
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix not in {
                    ".py",
                    ".ts",
                    ".js",
                    ".go",
                    ".rs",
                    ".java",
                }:
                    continue
                relative = path.relative_to(root).as_posix()
                if relative not in declared:
                    report.unlinked.append(relative)

    return report


def render(report: Report) -> str:
    """Human-readable form, used by the CLI and in tests."""
    lines = [
        f"decisions   : {len(report.decisions)}",
        f"declarations: {len(report.declarations)}",
    ]

    linked = len(report.declarations) - len(report.stale) - len(report.broken)
    lines.append(f"verified    : {linked}")

    if report.broken:
        lines += ["", f"BROKEN ({len(report.broken)}) — the decision does not exist"]
        for declaration, why in report.broken:
            lines.append(f"  {declaration.path}:{declaration.line}  {why}")

    if report.stale:
        lines += [
            "",
            f"STALE ({len(report.stale)}) — the decision changed after this was written",
        ]
        for declaration, why in report.stale:
            lines.append(f"  {declaration.path}:{declaration.line}  {why}")

    if report.unlinked:
        lines += ["", f"UNLINKED ({len(report.unlinked)}) — no declaration"]
        for path in report.unlinked[:20]:
            lines.append(f"  {path}")

    if report.ok and not report.unlinked:
        lines += ["", "every declaration matches the decision it names"]

    return "\n".join(lines)


def by_decision(report: Report) -> dict[str, list[Declaration]]:
    """The reverse index: which files declare each decision.

    This is the direction a reader wants — "what implements this decision?" — and the
    direction the dashboard and any impact analysis need.
    """
    index: dict[str, list[Declaration]] = {}
    for declaration in report.declarations:
        index.setdefault(declaration.decision_id, []).append(declaration)
    return index
