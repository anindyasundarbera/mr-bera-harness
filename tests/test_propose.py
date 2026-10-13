"""Tests for the proposal schema and the effect gates.

The point of step 4 is the split between what a provider can enforce and what
only the harness can. So the tests concentrate on:

* **structure is checked** — malformed proposals are rejected, including the
  conditional requirements that make an incomplete intent invalid;
* **meaning is checked too** — a *structurally valid* proposal that the schema
  permits can still be refused, which is the §10.1 finding made executable;
* **nothing executes** — the module has no path to a mutation, asserted rather
  than asserted-in-prose;
* **every §7.1 rule is covered** — a rule cannot be silently dropped.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from harness.cli import main
from harness.config import load_config
from harness.propose import gate as gate_module
from harness.propose.gate import (
    NOT_CHECKED,
    PERMITTED,
    REFUSED,
    RULES_ENFORCED,
    gate_proposal,
)
from harness.propose.schema import (
    INTENTS,
    PROPOSAL_SCHEMA,
    PROPOSAL_SCHEMA_VERSION,
    REQUIRED_BY_INTENT,
    validate_structure,
)

#: Proposal validation is an optional extra (`.[propose]`). Without it the suite
#: skips rather than fails: a consumer is not obliged to take a dependency whose
#: only purpose is gating proposals they may not use. CI installs the extra, so
#: these run there.
pytest.importorskip("jsonschema", reason="install the `propose` extra to test gates")

DIGEST = "a" * 64


def proposal(**overrides: object) -> dict:
    """A minimal well-formed proposal, overridden per test."""
    base: dict = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "work_id": "MRB-M06-S01",
        "intent": "create_branch",
        "summary": "Start work on the parser stage",
        "branch": "feat/parser",
    }
    base.update(overrides)
    return base


def write_proposal(**overrides: object) -> dict:
    base = proposal(intent="write_file")
    base.update(
        {"target_path": "src/parser.py", "work_packet": "WP-M06-001", "content_digest": DIGEST}
    )
    base.update(overrides)
    return base


class TestSchema:
    def test_a_minimal_proposal_is_valid(self) -> None:
        assert validate_structure(proposal()) == []

    def test_schema_version_is_pinned_by_const(self) -> None:
        assert validate_structure(proposal(schema_version=99)) != []

    def test_unknown_intent_is_invalid(self) -> None:
        """An intent the harness does not implement must not be proposable."""
        assert validate_structure(proposal(intent="delete_everything")) != []

    def test_extra_properties_are_rejected(self) -> None:
        """`additionalProperties: false` is what stops a key being smuggled in."""
        problems = validate_structure(proposal(injected="x"))
        assert any("Additional properties" in p for p in problems)

    def test_missing_required_field_is_invalid(self) -> None:
        bad = proposal()
        del bad["work_id"]
        assert validate_structure(bad) != []

    def test_empty_summary_is_invalid(self) -> None:
        assert validate_structure(proposal(summary="")) != []

    def test_a_non_object_is_invalid(self) -> None:
        assert validate_structure(["not", "an", "object"]) != []

    @pytest.mark.parametrize("intent", INTENTS)
    def test_every_intent_has_a_documented_requirement(self, intent: str) -> None:
        """The schema's conditionals and `REQUIRED_BY_INTENT` must agree."""
        assert intent in REQUIRED_BY_INTENT

    @pytest.mark.parametrize(
        ("intent", "field"),
        [(i, f) for i, fields in REQUIRED_BY_INTENT.items() for f in fields],
    )
    def test_a_conditional_requirement_is_enforced(self, intent: str, field: str) -> None:
        """An incomplete intent must be structurally invalid, not merely odd.

        This is what makes the schema worth enforcing: a provider that cannot
        express 'a write needs a packet' cannot be relied on to enforce it.
        """
        incomplete = proposal(intent=intent)
        incomplete.pop(field, None)
        problems = validate_structure(incomplete)
        assert any(field in p for p in problems), f"{intent} accepted without {field}"

    def test_schema_is_json_serializable_and_identified(self) -> None:

        json.dumps(PROPOSAL_SCHEMA)
        assert PROPOSAL_SCHEMA["$id"].endswith(f"proposal-v{PROPOSAL_SCHEMA_VERSION}.json")

    def test_schema_declares_additional_properties_false(self) -> None:
        """The setting that makes the schema strict enough to be worth handing over."""
        assert PROPOSAL_SCHEMA["additionalProperties"] is False

    def test_missing_validator_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No validator means no validation — never a silent pass."""
        import builtins  # noqa: PLC0415 - imported in the test that needs it

        from harness.propose.schema import (  # noqa: PLC0415 - imported in the test that needs it
            SchemaUnavailableError,
            validator,
        )

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "jsonschema":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(SchemaUnavailableError, match="pip install"):
            validator()


class TestRulesAreCovered:
    def test_every_architecture_rule_is_enforced(self) -> None:
        """§7.1 enumerates six rules; each must be cited by a gate."""
        expected = {
            "do not write code unless explicitly instructed",
            "switch to a new branch for new development",
            "test before push",
            "never commit a secret",
            "one logical change per branch",
            "write a decision, not a memory",
        }
        assert set(RULES_ENFORCED) == expected

    def test_every_gate_cites_a_known_rule(self) -> None:
        for fn in gate_module.ALL_GATES:
            source = inspect.getsource(fn)
            assert any(rule in source for rule in RULES_ENFORCED), fn.__name__


class TestNothingExecutes:
    """The property that makes 'the model executes nothing' true rather than a
    discipline: there is no code path from these modules to a mutation."""

    FORBIDDEN_IMPORTS = {
        "os",
        "shutil",
        "subprocess",
        "requests",
        "socket",
        "urllib",
    }
    FORBIDDEN_CALLS = {"open", "write_text", "write_bytes", "unlink", "rmtree", "remove"}

    def _tree(self, module_file: str) -> ast.Module:
        return ast.parse(Path(module_file).read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "module_file",
        [
            gate_module.__file__,
            __import__("harness.propose.schema", fromlist=["x"]).__file__,
        ],
    )
    def test_no_mutation_or_network_machinery_is_imported(self, module_file: str) -> None:
        imported: set[str] = set()
        for node in ast.walk(self._tree(module_file)):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & self.FORBIDDEN_IMPORTS), f"{module_file} imports {imported}"

    def test_no_file_is_opened(self, module_file: str = gate_module.__file__) -> None:
        called = {
            node.func.id
            for node in ast.walk(self._tree(module_file))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & self.FORBIDDEN_CALLS)

    def test_gating_has_no_side_effects(self, git_project: Path) -> None:
        """Gating twice must leave the tree exactly as it was."""
        before = sorted(p.relative_to(git_project).as_posix() for p in git_project.rglob("*"))
        for _ in range(3):
            gate_proposal(write_proposal(), config=load_config(git_project), manifest=["src/"])
        after = sorted(p.relative_to(git_project).as_posix() for p in git_project.rglob("*"))
        assert before == after


class TestGates:
    def test_a_clean_write_is_permitted(self, git_project: Path) -> None:
        verdict = gate_proposal(
            write_proposal(), config=load_config(git_project), manifest=["src/"]
        )
        assert verdict.may_execute
        assert verdict.summary() == "permitted"

    def test_every_gate_reports_a_verdict(self, git_project: Path) -> None:
        verdict = gate_proposal(proposal(), config=load_config(git_project), manifest=["src/"])
        assert len(verdict.gates) == len(gate_module.ALL_GATES)
        assert all(g.verdict in {PERMITTED, REFUSED, NOT_CHECKED} for g in verdict.gates)

    def test_structural_failure_short_circuits_meaning(self, git_project: Path) -> None:
        """A malformed proposal cannot be judged on meaning, so it is not."""
        verdict = gate_proposal({"nope": True}, config=load_config(git_project))
        assert verdict.structural_problems
        assert not verdict.may_execute
        assert verdict.gates == ()

    def test_a_non_object_is_refused_not_crashed(self, git_project: Path) -> None:
        verdict = gate_proposal("just a string", config=load_config(git_project))
        assert verdict.structural_problems
        assert not verdict.may_execute

    def test_secret_path_is_refused_even_with_a_packet(self, git_project: Path) -> None:
        """`never commit a secret` is not waived by any other precondition."""
        verdict = gate_proposal(
            write_proposal(target_path=".env"),
            config=load_config(git_project),
            manifest=["."],
        )
        assert not verdict.may_execute
        assert any(g.name == "secret-path" for g in verdict.refusals)

    @pytest.mark.parametrize("path", ["credentials.json", "deploy.pem", "a/b/key.p12"])
    def test_other_forbidden_paths_are_refused(self, git_project: Path, path: str) -> None:
        verdict = gate_proposal(
            write_proposal(target_path=path), config=load_config(git_project), manifest=["."]
        )
        assert not verdict.may_execute

    def test_env_example_is_still_writable(self, git_project: Path) -> None:
        """A template without values must remain committable, or nobody can
        document which keys exist."""
        verdict = gate_proposal(
            write_proposal(target_path=".env.example"),
            config=load_config(git_project),
            manifest=["."],
        )
        assert verdict.may_execute

    @pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "a/../../b"])
    def test_paths_escaping_the_root_are_refused(self, git_project: Path, path: str) -> None:
        verdict = gate_proposal(
            write_proposal(target_path=path), config=load_config(git_project), manifest=["."]
        )
        assert not verdict.may_execute
        assert any(g.name == "path-escapes-root" for g in verdict.refusals)

    def test_a_write_without_a_packet_is_refused(self, git_project: Path) -> None:
        no_packet = write_proposal()
        del no_packet["work_packet"]
        verdict = gate_proposal(no_packet, config=load_config(git_project), manifest=["src/"])
        # Structurally invalid, because the schema requires it — the strongest
        # form of the rule: the provider cannot even express the proposal.
        assert not verdict.may_execute

    def test_push_without_a_passing_test_is_refused(self, git_project: Path) -> None:
        verdict = gate_proposal(
            proposal(intent="push", branch="feat/x"),
            config=load_config(git_project),
            manifest=["src/"],
        )
        assert not verdict.may_execute
        assert any(g.name == "test-before-push" for g in verdict.refusals)

    def test_push_after_a_passing_test_is_permitted(self, git_project: Path) -> None:
        verdict = gate_proposal(
            proposal(intent="push", branch="feat/x", test_effect_passed=True),
            config=load_config(git_project),
            manifest=["src/"],
        )
        assert verdict.may_execute

    def test_push_to_a_protected_branch_is_refused(self, git_project: Path) -> None:
        """The adversarial case §10.1 says the schema cannot catch.

        A `push` to `main` with `test_effect_passed: true` is fully
        schema-valid — a provider enforcing only the schema would let it through.
        The gate is where it is stopped.
        """
        payload = proposal(intent="push", branch="main", test_effect_passed=True)
        assert validate_structure(payload) == [], "the schema is expected to allow this"
        verdict = gate_proposal(payload, config=load_config(git_project), manifest=["src/"])
        assert not verdict.may_execute
        assert any(g.name == "branch-policy" for g in verdict.refusals)

    def test_creating_a_branch_on_main_is_refused(self, git_project: Path) -> None:
        """`branch` is the branch the proposal *names*, so creating `main` targets
        a protected branch rather than leaving one.

        Refusing to *start* a session on a protected branch is the session
        guard's job; this gate judges the named branch.
        """
        verdict = gate_proposal(
            proposal(intent="create_branch", branch="main"), config=load_config(git_project)
        )
        assert not verdict.may_execute
        assert any(g.name == "branch-policy" for g in verdict.refusals)

    def test_creating_a_feature_branch_is_permitted(self, git_project: Path) -> None:
        """The intent that leaves a protected branch, and the first harness action."""
        verdict = gate_proposal(
            proposal(intent="create_branch", branch="feat/parser"),
            config=load_config(git_project),
        )
        assert verdict.may_execute

    @pytest.mark.parametrize("branch", ["evil-feat/x", "feat", "feature/x", "FEAT/x"])
    def test_branch_prefix_must_match_configured_policy(
        self, git_project: Path, branch: str
    ) -> None:
        verdict = gate_proposal(
            proposal(intent="push", branch=branch, test_effect_passed=True),
            config=load_config(git_project),
            manifest=["src/"],
        )
        assert not verdict.may_execute

    def test_a_decision_without_an_entry_is_refused(self, git_project: Path) -> None:
        verdict = gate_proposal(
            proposal(intent="record_decision", entry_id=""), config=load_config(git_project)
        )
        # Empty entry_id fails the schema's minLength, so it never reaches the gate.
        assert not verdict.may_execute

    def test_a_decision_with_an_entry_is_permitted(self, git_project: Path) -> None:
        verdict = gate_proposal(
            proposal(intent="record_decision", entry_id="ADR-2026-012"),
            config=load_config(git_project),
        )
        assert verdict.may_execute

    def test_a_path_outside_the_manifest_is_refused(self, git_project: Path) -> None:
        verdict = gate_proposal(
            write_proposal(target_path="docs/other.md"),
            config=load_config(git_project),
            manifest=["src/"],
        )
        assert not verdict.may_execute
        assert any(g.name == "change-manifest" for g in verdict.refusals)

    def test_a_whole_project_manifest_covers_every_path(self, git_project: Path) -> None:
        """A manifest of `.` means "any path in the project"."""
        verdict = gate_proposal(
            write_proposal(target_path="anywhere/at/all.md"),
            config=load_config(git_project),
            manifest=["."],
        )
        assert verdict.may_execute

    def test_a_path_inside_the_manifest_is_permitted(self, git_project: Path) -> None:
        verdict = gate_proposal(
            write_proposal(target_path="src/deep/parser.py"),
            config=load_config(git_project),
            manifest=["src/"],
        )
        assert verdict.may_execute

    def test_no_manifest_is_not_checked_not_permitted(self, git_project: Path) -> None:
        """A rule that cannot be evaluated must not pass."""
        verdict = gate_proposal(write_proposal(), config=load_config(git_project), manifest=None)
        assert not verdict.may_execute
        assert verdict.unchecked
        assert "not checked" in verdict.summary()

    def test_request_permission_is_permitted(self, git_project: Path) -> None:
        """Asking a human is a request, not a mutation, so nothing gates it."""
        verdict = gate_proposal(
            proposal(intent="request_permission", requested_action="push to main"),
            config=load_config(git_project),
        )
        assert verdict.may_execute

    def test_verdict_is_json_serializable(self, git_project: Path) -> None:

        verdict = gate_proposal(
            write_proposal(), config=load_config(git_project), manifest=["src/"]
        )
        json.dumps(verdict.as_dict())

    def test_gating_is_deterministic(self, git_project: Path) -> None:
        config = load_config(git_project)
        first = gate_proposal(write_proposal(), config=config, manifest=["src/"]).as_dict()
        second = gate_proposal(write_proposal(), config=config, manifest=["src/"]).as_dict()
        assert first == second


class TestCLI:
    def _run(self, args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:

        monkeypatch.chdir(tmp_path)
        return main(args)

    def test_schema_prints_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["propose", "schema"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["$id"].endswith("proposal-v1.json")

    def test_validate_invalid_is_one(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"nope": 1}), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "validate", str(path)]) == 1

    def test_validate_valid_is_zero(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps(proposal()), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "validate", str(path)]) == 0

    def test_gate_permitted_is_zero(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps(write_proposal()), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "gate", str(path), "--manifest", "src/"]) == 0

    def test_gate_refused_is_two(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps(write_proposal(target_path=".env")), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "gate", str(path), "--manifest", "."]) == 2

    def test_gate_not_checked_is_three(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps(write_proposal()), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "gate", str(path)]) == 3

    def test_bad_json_is_a_usage_error(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "gate", str(path)]) == 4

    def test_json_verdict_is_parseable(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps(write_proposal()), encoding="utf-8")
        monkeypatch.chdir(git_project)
        assert main(["propose", "gate", str(path), "--manifest", "src/", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["may_execute"] is True
        assert len(payload["gates"]) == len(gate_module.ALL_GATES)
