"""Tests for instruction→work-item resolution.

This is the one step the architecture rates **not deterministic**, so the tests
concentrate on the property that keeps it safe: **it must refuse rather than guess.**

Three things are asserted repeatedly, because they are what a wrong answer would
cost:

* an identifier written in the instruction is used exactly, never re-inferred;
* a tie, or a close runner-up, is `ambiguous` — no winner is chosen;
* nothing that resolves can execute anything; resolution feeds the compiler, which
  is also deterministic.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

from harness.cli import main
from harness.config import load_config
from harness.intent.resolve import (
    AMBIGUOUS,
    EXIT_AMBIGUOUS,
    EXIT_OK,
    EXIT_UNRESOLVED,
    RESOLVED,
    UNRESOLVED,
    Candidate,
    Resolution,
    exact_mentions,
    known_work_ids,
    render,
    resolve,
    scan_pattern,
    score,
)


@pytest.fixture
def config(git_project: Path):
    return load_config(git_project)


class TestScanPattern:
    """The scan pattern must accept the same grammar as the validator, unanchored.

    Getting this wrong initially produced an identifier-naming instruction that
    resolved to *nothing* — the failure this class pins.
    """

    def test_it_is_unanchored(self, config) -> None:
        assert not scan_pattern(config).pattern.startswith("\\A")

    def test_it_finds_one_level(self, config) -> None:
        assert exact_mentions("see MRB-M06", scan_pattern(config)) == ["MRB-M06"]

    def test_it_finds_two_levels(self, config) -> None:
        assert exact_mentions("MRB-M06-S07", scan_pattern(config)) == ["MRB-M06-S07"]

    def test_it_finds_one_inside_prose(self, config) -> None:
        """The bug: `re.search` with an anchored pattern never matches a substring."""
        assert exact_mentions("please work on MRB-M06-S07 today", scan_pattern(config)) == [
            "MRB-M06-S07"
        ]

    def test_levels_stay_optional_and_nested(self, config) -> None:
        """Concatenating the level groups makes every level mandatory."""
        pattern = scan_pattern(config)
        assert pattern.search("MRB-M06")
        assert pattern.search("MRB-M06-S07")

    def test_it_finds_nothing_in_unrelated_text(self, config) -> None:
        assert exact_mentions("fix the parser", scan_pattern(config)) == []

    def test_mentions_are_deduplicated_in_order(self, config) -> None:
        found = exact_mentions("MRB-M06-S07 then MRB-M06 then MRB-M06-S07", scan_pattern(config))
        assert found == ["MRB-M06-S07", "MRB-M06"]

    def test_a_consumer_grammar_is_respected(self, tmp_path: Path) -> None:
        """Derived from configuration, so a different project's IDs are found."""

        root = tmp_path / "consumer"
        for sub in ("docs", "kb", "tests", "tools"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        (root / "harness.toml").write_text(
            '[identity]\nname = "C"\nid_prefix = "JOB"\nlevels = ["A"]\nwidths = [3]\n'
            '[paths]\ndocs = "docs"\nknowledge = "kb"\n',
            encoding="utf-8",
        )
        # levels/widths must correspond; the loader rejects a mismatch.
        cfg = load_config(root)
        # widths=[3], so the identifier has three digits. `JOB-A01` would be
        # malformed and correctly not match — which is the grammar doing its job.
        assert exact_mentions("do JOB-A001", scan_pattern(cfg)) == ["JOB-A001"]
        assert exact_mentions("do JOB-A01", scan_pattern(cfg)) == []
        assert exact_mentions("do MRB-M06", scan_pattern(cfg)) == []


class TestKnownIds:
    def test_ids_come_from_the_decomposition(self, config, git_project: Path) -> None:
        """The project declares what work exists; this invents no list."""
        ids = known_work_ids(config)
        assert "MRB-M06" in ids
        assert "MRB-M06-S07" in ids

    def test_a_project_without_a_decomposition_has_no_ids(self, tmp_path: Path) -> None:
        for sub in ("docs", "kb", "tests", "tools"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / "harness.toml").write_text(
            '[paths]\ndocs = "docs"\nknowledge = "kb"\n', encoding="utf-8"
        )
        assert known_work_ids(load_config(tmp_path)) == {}


class TestScoring:
    def test_overlap_scores_above_zero(self) -> None:
        candidate = Candidate("MRB-M06", title="Provider registry and model set")
        assert score("model set", candidate) > 0

    def test_unrelated_text_scores_zero(self) -> None:
        assert score("zzz nothing like it", Candidate("MRB-M06", title="Provider registry")) == 0.0

    def test_scoring_is_deterministic(self) -> None:
        candidate = Candidate("MRB-M06", title="Provider registry and model set")
        assert score("model set", candidate) == score("model set", candidate)

    def test_concepts_widen_the_description(self) -> None:
        """A phrase can reach an id through the concepts that cover it."""
        bare = Candidate("MRB-M06", title="")
        enriched = Candidate("MRB-M06", title="", concepts=("Model Set and Hardware Envelope",))
        assert score("hardware envelope", enriched) > score("hardware envelope", bare)

    def test_stopwords_carry_no_signal(self) -> None:
        assert score("the of and", Candidate("MRB-M06", title="the of and")) == 0.0


class TestResolutionRefusesRatherThanGuesses:
    def test_one_named_identifier_resolves(self, config) -> None:
        outcome = resolve(config, "work on MRB-M06-S07")
        assert outcome.status == RESOLVED
        assert outcome.chosen == "MRB-M06-S07"
        assert outcome.exit_code() == EXIT_OK

    def test_a_named_identifier_is_not_re_inferred(self, config) -> None:
        """An identifier the person wrote is exact, so scoring is not consulted."""
        outcome = resolve(config, "MRB-M06-S07 is what I mean, not the other one")
        assert outcome.chosen == "MRB-M06-S07"
        assert "exactly one work identifier" in outcome.reason

    def test_two_named_identifiers_is_ambiguous(self, config) -> None:
        outcome = resolve(config, "MRB-M06 and MRB-M06-S07")
        assert outcome.status == AMBIGUOUS
        assert outcome.chosen is None
        assert outcome.exit_code() == EXIT_AMBIGUOUS

    def test_nothing_matching_is_unresolved(self, config) -> None:
        outcome = resolve(config, "zzz nothing like this at all")
        assert outcome.status == UNRESOLVED
        assert outcome.chosen is None
        assert outcome.exit_code() == EXIT_UNRESOLVED

    def test_a_close_runner_up_is_ambiguous_even_with_a_leader(self, tmp_path: Path) -> None:
        """A leader is not a decision: a close second means the answer is a question.

        Built deliberately, with two titles that share most of their words, because
        the shared fixture's titles happen to be unambiguous.
        """
        root = tmp_path / "close"
        for sub in ("docs", "kb", "tests", "tools"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        (root / "harness.toml").write_text(
            '[identity]\nname = "C"\nid_prefix = "MRB"\nlevels = ["M"]\nwidths = [2]\n'
            '[paths]\ndocs = "docs"\nknowledge = "kb"\n',
            encoding="utf-8",
        )
        (root / "docs" / "PROJECT_DECOMPOSITION.md").write_text(
            "- MRB-M01 — provider registry and model set\n"
            "- MRB-M02 — provider registry and model limits\n",
            encoding="utf-8",
        )
        cfg = load_config(root)
        # A phrase the two share almost entirely: neither title contains it
        # verbatim, so this is a genuinely close call rather than a clear leader.
        outcome = resolve(cfg, "provider registry model")
        assert outcome.status == AMBIGUOUS, outcome.reason
        assert outcome.chosen is None
        assert "ask which" in outcome.reason

    def test_a_verbatim_title_is_a_clear_leader_not_an_ambiguity(self, tmp_path: Path) -> None:
        """The converse: closeness is measured, so an exact match still resolves."""
        root = tmp_path / "exact"
        for sub in ("docs", "kb", "tests", "tools"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        (root / "harness.toml").write_text(
            '[identity]\nname = "C"\nid_prefix = "MRB"\nlevels = ["M"]\nwidths = [2]\n'
            '[paths]\ndocs = "docs"\nknowledge = "kb"\n',
            encoding="utf-8",
        )
        (root / "docs" / "PROJECT_DECOMPOSITION.md").write_text(
            "- MRB-M01 — provider registry and model set\n"
            "- MRB-M02 — provider registry and model limits\n",
            encoding="utf-8",
        )
        cfg = load_config(root)
        outcome = resolve(cfg, "provider registry and model set")
        assert outcome.status == RESOLVED
        assert outcome.chosen == "MRB-M01"

    def test_an_unresolved_outcome_proposes_names_rather_than_picking(self, config) -> None:
        assert "name the work item rather than guessing" in resolve(config, "zzz").reason

    def test_resolution_never_returns_a_choice_when_must_clarify(self, config) -> None:
        for instruction in ("MRB-M06 and MRB-M07", "zzz nothing"):
            outcome = resolve(config, instruction)
            assert outcome.must_clarify
            assert outcome.chosen is None, instruction

    def test_threshold_is_honoured(self, config) -> None:
        """A higher cut can turn a resolution into an unresolved, never a different pick."""
        low = resolve(config, "model set and hardware envelope", threshold=0.1)
        high = resolve(config, "model set and hardware envelope", threshold=0.99)
        assert high.status == UNRESOLVED
        assert high.chosen is None
        assert low.status in {RESOLVED, AMBIGUOUS}

    def test_resolution_is_deterministic(self, config) -> None:
        first = resolve(config, "model set and hardware envelope").as_dict()
        second = resolve(config, "model set and hardware envelope").as_dict()
        assert first == second

    def test_outcome_is_json_serializable(self, config) -> None:
        json.dumps(resolve(config, "MRB-M06").as_dict())
        json.dumps(resolve(config, "zzz").as_dict())

    def test_an_undeclared_identifier_still_resolves_with_a_caveat(self, config) -> None:
        """New work is legitimate; the reason says the decomposition does not know it."""
        outcome = resolve(config, "start MRB-M99")
        assert outcome.status == RESOLVED
        assert outcome.chosen == "MRB-M99"
        assert "does not declare" in outcome.reason


class TestRender:
    def test_it_shows_the_reason(self, config) -> None:
        text = render(resolve(config, "MRB-M06"), config)
        assert "work item   : MRB-M06" in text

    def test_it_asks_for_clarification_when_ambiguous(self, config) -> None:
        text = render(resolve(config, "MRB-M06 and MRB-M07"), config)
        assert "Ask the person which work item" in text

    def test_it_does_not_ask_when_resolved(self, config) -> None:
        text = render(resolve(config, "MRB-M06"), config)
        assert "Ask the person" not in text

    def test_an_explicit_bypass_is_not_described_as_inference(self, config) -> None:
        """The architecture's point: a human naming the ID loses nothing."""
        outcome = Resolution(
            instruction="anything",
            status=RESOLVED,
            chosen="MRB-M06",
            reason="the work item was given explicitly, so nothing was inferred",
        )
        assert "nothing was inferred" in render(outcome, config)


class TestNothingExecutes:
    def test_resolution_touches_no_network_and_no_shell(self) -> None:
        forbidden = {"socket", "http", "urllib", "requests", "subprocess", "shutil", "os"}
        module_file = importlib.import_module("harness.intent.resolve").__file__
        tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden), f"imports {imported & forbidden}"

    def test_resolving_writes_nothing(self, git_project: Path) -> None:
        def tree_state() -> list[str]:
            return sorted(p.relative_to(git_project).as_posix() for p in git_project.rglob("*"))

        before = tree_state()
        for instruction in ("MRB-M06", "zzz", "MRB-M06 and MRB-M07"):
            resolve(load_config(git_project), instruction)
        assert tree_state() == before


class TestCLI:
    def test_resolved_is_zero(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "work on MRB-M06-S07"]) == 0
        assert "status      : resolved" in capsys.readouterr().out

    def test_ambiguous_is_three(self, git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "MRB-M06 and MRB-M06-S07"]) == 3

    def test_unresolved_is_four(self, git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "zzz nothing here"]) == 4

    def test_explicit_work_id_bypasses_resolution(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "anything at all", "--work-id", "MRB-M06"]) == 0
        out = capsys.readouterr().out
        assert "nothing was inferred" in out

    def test_a_malformed_explicit_id_is_a_usage_error(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "x", "--work-id", "NOT-AN-ID"]) == 2

    def test_json_is_parseable(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "MRB-M06", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["chosen"] == "MRB-M06"
        assert payload["status"] == RESOLVED

    def test_it_chains_into_the_compiler(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Resolution feeds step 3, which is itself deterministic."""
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "MRB-M06", "--budget", "100000"]) == 0
        assert "fingerprint" in capsys.readouterr().err

    def test_a_blocked_item_still_refuses_at_the_compiler(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolution is not a gate: the compiler's refusals still apply."""
        monkeypatch.chdir(git_project)
        assert main(["intent", "resolve", "MRB-M06-S07", "--budget", "100000"]) == 3
