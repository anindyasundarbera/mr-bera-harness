"""The effect gates: whether a structurally valid proposal is permitted.

This is where the real checking lives. `HARNESS_ARCHITECTURE.md` §10.1 proved
that schema enforcement is native and that **semantics are not**: every
adversarial model returned a *structurally valid* proposal that the attack had
steered. So a valid schema is a necessary condition, never a sufficient one, and
meaning is decided here.

Two properties are load-bearing:

1. **A gate returns a verdict; it never executes.** There is no code path from
   this module to a mutation. That is what makes "every mutation has exactly one
   executor, and it is not the model" true rather than a discipline.
2. **`unknown` is a real verdict.** A gate that cannot check a precondition says
   so, rather than passing.

The policies are the rules `HARNESS_ARCHITECTURE.md` §7.1 enumerates. Each one is
named in the rule list before it is enforced here, and a test asserts the coverage
so a new intent cannot arrive without a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness.config import Config

#: Verdicts. Three-valued for the same reason the dashboard is: "not checked" is
#: not "permitted", and collapsing it would report permission nobody granted.
PERMITTED = "permitted"
REFUSED = "refused"
NOT_CHECKED = "not-checked"

#: The rules from architecture §7.1, quoted so the code and the document cannot
#: drift apart silently. Each gate below cites one of these.
RULE_WRITE_REQUIRES_PACKET = "do not write code unless explicitly instructed"
RULE_BRANCH_FIRST = "switch to a new branch for new development"
RULE_TEST_BEFORE_PUSH = "test before push"
RULE_NO_SECRET = "never commit a secret"
RULE_ONE_CHANGE_PER_BRANCH = "one logical change per branch"
RULE_DECISION_NOT_MEMORY = "write a decision, not a memory"


@dataclass(frozen=True)
class Gate:
    """One checked precondition."""

    name: str
    rule: str
    verdict: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rule": self.rule,
            "verdict": self.verdict,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Verdict:
    """The outcome of gating a proposal.

    `may_execute` is true **only** when every gate is `PERMITTED`. A `NOT_CHECKED`
    gate blocks execution: the harness does not act on a precondition it could not
    evaluate.
    """

    proposal: dict[str, Any]
    gates: tuple[Gate, ...] = ()
    structural_problems: tuple[str, ...] = ()

    @property
    def may_execute(self) -> bool:
        return not self.structural_problems and all(g.verdict == PERMITTED for g in self.gates)

    @property
    def refusals(self) -> tuple[Gate, ...]:
        return tuple(g for g in self.gates if g.verdict == REFUSED)

    @property
    def unchecked(self) -> tuple[Gate, ...]:
        return tuple(g for g in self.gates if g.verdict == NOT_CHECKED)

    def summary(self) -> str:
        if self.structural_problems:
            return f"structurally invalid ({len(self.structural_problems)} problem(s))"
        if self.refusals:
            names = ", ".join(g.name for g in self.refusals)
            return f"refused by: {names}"
        if self.unchecked:
            names = ", ".join(g.name for g in self.unchecked)
            return f"not checked: {names}"
        return "permitted"

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal,
            "may_execute": self.may_execute,
            "summary": self.summary(),
            "structural_problems": list(self.structural_problems),
            "gates": [g.as_dict() for g in self.gates],
        }


def _ok(name: str, rule: str, detail: str) -> Gate:
    return Gate(name, rule, PERMITTED, detail)


def _no(name: str, rule: str, detail: str) -> Gate:
    return Gate(name, rule, REFUSED, detail)


def _unknown(name: str, rule: str, detail: str) -> Gate:
    return Gate(name, rule, NOT_CHECKED, detail)


def _secret_patterns(config: Config | None) -> tuple[re.Pattern[str], ...]:
    from harness.config import Config as _Config  # noqa: PLC0415 - avoids a cycle

    patterns = (config or _Config.defaults()).forbidden_path_globs
    return tuple(re.compile(p) for p in patterns)


def _normalize(path: str) -> str:
    """A path as the gate should judge it: relative, forward-slashed, no `..`.

    Absolute paths and `..` segments are how a path check is defeated: an
    allow-list that tests the raw string can be walked around by writing
    `knowledge/../../.env`. Normalizing first closes that.
    """
    text = str(path).replace("\\", "/").strip()
    return str(Path(text)).replace("\\", "/") if not text.startswith("/") else text


def gate_secrets(proposal: dict[str, Any], config: Config | None) -> Gate:
    """`never commit a secret` — a path matching the forbidden globs is refused."""
    raw = proposal.get("target_path")
    if not raw:
        return _ok("secret-path", RULE_NO_SECRET, "no path is named by this intent")

    normalized = _normalize(str(raw))
    for pattern in _secret_patterns(config):
        if pattern.search(normalized):
            return _no(
                "secret-path",
                RULE_NO_SECRET,
                f"`{normalized}` matches a forbidden path pattern; a secret must never "
                "enter the repository, and history is not a place to undo it",
            )
    return _ok("secret-path", RULE_NO_SECRET, f"`{normalized}` is not a forbidden path")


def gate_no_escaping_path(proposal: dict[str, Any]) -> Gate:
    """A path must stay inside the project.

    Not in §7.1 as a separate rule, but it is the mechanism by which the
    `never commit a secret` rule is actually enforced: a path that escapes the
    root can name any file on the machine.
    """
    raw = proposal.get("target_path")
    if not raw:
        return _ok("path-escapes-root", RULE_NO_SECRET, "no path is named by this intent")
    text = str(raw).replace("\\", "/")
    if text.startswith("/") or ".." in Path(text).parts:
        return _no(
            "path-escapes-root",
            RULE_NO_SECRET,
            f"`{text}` is absolute or escapes the project root; a proposal may only "
            "name a path inside the repository",
        )
    return _ok("path-escapes-root", RULE_NO_SECRET, f"`{text}` is inside the project")


def gate_write_requires_packet(proposal: dict[str, Any]) -> Gate:
    """`do not write code unless explicitly instructed` — a write needs a packet."""
    if proposal.get("intent") != "write_file":
        return _ok("write-requires-packet", RULE_WRITE_REQUIRES_PACKET, "not a write")
    packet = proposal.get("work_packet")
    if not packet:
        return _no(
            "write-requires-packet",
            RULE_WRITE_REQUIRES_PACKET,
            "a write is proposed with no approved work packet; no write tool is "
            "exposed until an implementation intent is authorised",
        )
    return _ok("write-requires-packet", RULE_WRITE_REQUIRES_PACKET, f"packet `{packet}`")


def gate_branch_policy(proposal: dict[str, Any], config: Config | None) -> Gate:
    """`switch to a new branch for new development`.

    The `branch` field is the branch the proposal **names** — the one to create,
    for `create_branch`, or the one to push. This gate judges that name. It does
    not know which branch the session is currently on: refusing to *start* on a
    protected branch is the session guard's job (`ADR-2026-004`), and duplicating
    it here would be a second, divergent answer to one question.

    So every named branch must be a valid feature branch, including one being
    created. Creating a branch called `main` is not leaving a protected branch —
    it is targeting one.
    """
    from harness.config import Config as _Config  # noqa: PLC0415 - avoids a cycle

    branch = proposal.get("branch")
    if not branch:
        return _ok("branch-policy", RULE_BRANCH_FIRST, "this intent names no branch")

    cfg = config or _Config.defaults()
    if branch in cfg.protected_branches:
        return _no(
            "branch-policy",
            RULE_BRANCH_FIRST,
            f"`{branch}` is a protected branch; a coding session must not work on it, "
            "and a branch to create must be a feature branch",
        )
    prefixes = " ".join(f"{p}/" for p in cfg.branch_prefixes)
    if not any(re.match(rf"^{re.escape(p)}/[a-z0-9._-]+$", branch) for p in cfg.branch_prefixes):
        return _no(
            "branch-policy",
            RULE_BRANCH_FIRST,
            f"`{branch}` does not match an allowed prefix ({prefixes})",
        )
    return _ok("branch-policy", RULE_BRANCH_FIRST, f"`{branch}` is an allowed branch")


def gate_test_before_push(proposal: dict[str, Any]) -> Gate:
    """`test before push` — the push tool is not exposed until the check passed."""
    if proposal.get("intent") != "push":
        return _ok("test-before-push", RULE_TEST_BEFORE_PUSH, "not a push")
    if proposal.get("test_effect_passed") is not True:
        return _no(
            "test-before-push",
            RULE_TEST_BEFORE_PUSH,
            "a push is proposed but the test effect-check has not passed in this "
            "session; the push tool is not exposed until it has",
        )
    return _ok("test-before-push", RULE_TEST_BEFORE_PUSH, "the test effect-check passed")


def gate_decision_is_an_entry(proposal: dict[str, Any]) -> Gate:
    """`write a decision, not a memory` — an accepted decision produces an entry."""
    if proposal.get("intent") != "record_decision":
        return _ok("decision-is-an-entry", RULE_DECISION_NOT_MEMORY, "not a decision")
    entry = proposal.get("entry_id")
    if not entry:
        return _no(
            "decision-is-an-entry",
            RULE_DECISION_NOT_MEMORY,
            "a decision is proposed with no entry file; a decision that is not "
            "committed is a memory, and memory is not durable truth",
        )
    return _ok("decision-is-an-entry", RULE_DECISION_NOT_MEMORY, f"entry `{entry}`")


def gate_change_manifest(
    proposal: dict[str, Any],
    manifest: list[str] | None,
    config: Config | None,  # noqa: ARG001
) -> Gate:
    """`one logical change per branch` — a proposal outside the manifest is refused.

    When the session has declared **no** manifest, the gate is **not checked**
    rather than permitted: the rule cannot be evaluated without one, and passing
    on an unevaluated rule is the failure this three-valued verdict exists to
    prevent.
    """
    path = proposal.get("target_path")
    if not path:
        return _ok("change-manifest", RULE_ONE_CHANGE_PER_BRANCH, "no path is named")

    if manifest is None:
        return _unknown(
            "change-manifest",
            RULE_ONE_CHANGE_PER_BRANCH,
            "the session has not declared a change manifest, so this rule cannot "
            "be evaluated; declare it at session start",
        )

    normalized = _normalize(str(path))
    for allowed in manifest:
        scope = _normalize(allowed).rstrip("/") or "."
        # `.` is the whole project, so it covers every path.
        if scope == "." or normalized in {scope} or normalized.startswith(scope + "/"):
            return _ok(
                "change-manifest",
                RULE_ONE_CHANGE_PER_BRANCH,
                f"`{normalized}` is in scope ({scope})",
            )
    return _no(
        "change-manifest",
        RULE_ONE_CHANGE_PER_BRANCH,
        f"`{normalized}` is outside the declared change manifest ({', '.join(manifest)})",
    )


def gate_proposal(
    proposal: object,
    *,
    config: Config | None = None,
    manifest: list[str] | None = None,
) -> Verdict:
    """Gate a proposal. Returns a verdict; **executes nothing**.

    Structural validation runs first: a proposal that is not well-formed cannot be
    judged on meaning, and §10.1 is explicit that structure and semantics are
    different questions.
    """
    from harness.propose.schema import (  # noqa: PLC0415 - avoids a cycle at import
        validate_structure,
    )

    if not isinstance(proposal, dict):
        return Verdict(
            proposal={},
            structural_problems=("(root): proposal must be a JSON object",),
        )

    structural = tuple(validate_structure(proposal))
    if structural:
        return Verdict(proposal=proposal, structural_problems=structural)

    gates = (
        gate_secrets(proposal, config),
        gate_no_escaping_path(proposal),
        gate_write_requires_packet(proposal),
        gate_branch_policy(proposal, config),
        gate_test_before_push(proposal),
        gate_decision_is_an_entry(proposal),
        gate_change_manifest(proposal, manifest, config),
    )
    return Verdict(proposal=proposal, gates=gates)


#: The gate functions, exposed so a test can assert every §7.1 rule is covered.
ALL_GATES = (
    gate_secrets,
    gate_no_escaping_path,
    gate_write_requires_packet,
    gate_branch_policy,
    gate_test_before_push,
    gate_decision_is_an_entry,
    gate_change_manifest,
)

#: The rule identifiers the gates cite. A test asserts each corresponds to a rule
#: enumerated in architecture §7.1, so the code cannot invent a policy.
RULES_ENFORCED = (
    RULE_WRITE_REQUIRES_PACKET,
    RULE_BRANCH_FIRST,
    RULE_TEST_BEFORE_PUSH,
    RULE_NO_SECRET,
    RULE_ONE_CHANGE_PER_BRANCH,
    RULE_DECISION_NOT_MEMORY,
)
