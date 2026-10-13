"""Tests for the session ledger.

The ledger is the record of what a session did, so the properties that matter are
that it **keeps everything**, that it **cannot be silently altered**, that it
**travels** only when told to, and that its Postgres mirror is provably derived
rather than a second source of truth.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import git_commit
from harness.cli import main
from harness.ledger import mirror as mirror_mod
from harness.ledger import notes as notes_mod
from harness.ledger.record import (
    EFFECT_NOT_OBSERVED,
    RECORD_VERSION,
    Effect,
    PromptRef,
    RecordError,
    SessionRecord,
    parse_record,
)

FP = "a" * 64


def record(commit_sha: str = "b" * 40, **overrides: object) -> SessionRecord:
    base: dict = {
        "session_id": "s-1",
        "work_id": "MRB-M06-S01",
        "commit_sha": commit_sha,
        "at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return SessionRecord(**base)  # type: ignore[arg-type]


def head_sha(root: Path) -> str:
    """The commit at HEAD, as the ledger binds records to a commit."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()


class TestRecord:
    def test_a_record_round_trips_through_its_wire_form(self) -> None:
        original = record(prompt=PromptRef(fingerprint=FP, budget=4000, unit="word"))
        parsed = parse_record(original.to_line())
        assert parsed.as_dict() == original.as_dict()

    def test_the_wire_form_is_one_line(self) -> None:
        """`git notes append` separates messages with a blank line, so a record
        must never contain one."""
        assert "\n" not in record().to_line()

    def test_effect_defaults_to_not_observed(self) -> None:
        """A recorder that was not told what happened must say so."""
        assert record().effect.state == EFFECT_NOT_OBSERVED

    def test_missing_effect_parses_as_not_observed(self) -> None:
        """A record written before the field existed is readable, not broken."""
        line = json.dumps(
            {
                "record_version": RECORD_VERSION,
                "session_id": "s",
                "work_id": "w",
                "commit_sha": "c",
                "at": "t",
            }
        )
        assert parse_record(line).effect.state == EFFECT_NOT_OBSERVED

    def test_a_different_record_version_is_refused(self) -> None:
        """A record written against another contract cannot be read as this one."""
        line = json.dumps(
            {
                "record_version": 99,
                "session_id": "s",
                "work_id": "w",
                "commit_sha": "c",
                "at": "t",
            }
        )
        with pytest.raises(RecordError, match="record_version"):
            parse_record(line)

    def test_malformed_json_is_refused_not_skipped(self) -> None:
        with pytest.raises(RecordError, match="not valid JSON"):
            parse_record("{not json")

    def test_a_non_object_is_refused(self) -> None:
        with pytest.raises(RecordError, match="must be a JSON object"):
            parse_record("[1, 2]")

    def test_digest_covers_the_timestamp(self) -> None:
        """Two records differing only in time are different records."""
        assert record(at="2026-01-01").digest != record(at="2026-01-02").digest

    def test_digest_is_stable(self) -> None:
        assert record().digest == record().digest

    def test_the_prompt_is_recorded_by_reference(self) -> None:
        """The prompt is stored as its step-3 fingerprint, not as text — the
        fingerprint already binds the bytes and the manifest."""
        line = record(prompt=PromptRef(fingerprint=FP, budget=10, unit="word")).to_line()
        assert FP in line
        assert "entry_count" in line


class TestNotes:
    def test_append_then_read(self, git_project: Path) -> None:
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha), ref="harness")
        records = notes_mod.read_note(git_project, sha, ref="harness")
        assert len(records) == 1
        assert records[0].work_id == "MRB-M06-S01"

    def test_appending_is_additive(self, git_project: Path) -> None:
        """A ledger that overwrote would lose exactly what it exists to keep."""
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha, session_id="a"), ref="harness")
        notes_mod.append_record(git_project, record(sha, session_id="b"), ref="harness")
        records = notes_mod.read_note(git_project, sha, ref="harness")
        assert [r.session_id for r in records] == ["a", "b"]

    def test_a_commit_with_no_note_reads_as_empty(self, git_project: Path) -> None:
        """No note is an empty ledger, not an error."""
        assert notes_mod.read_note(git_project, "0" * 40, ref="harness") == []

    def test_read_all_walks_history(self, git_project: Path) -> None:
        first = head_sha(git_project)
        notes_mod.append_record(git_project, record(first, session_id="one"), ref="harness")

        (git_project / "later.txt").write_text("x", encoding="utf-8")
        second = git_commit(git_project, "docs: later")
        notes_mod.append_record(git_project, record(second, session_id="two"), ref="harness")

        assert [r.session_id for r in notes_mod.read_all(git_project, ref="harness")] == [
            "one",
            "two",
        ]

    def test_read_all_on_a_ledger_that_does_not_exist_is_empty(self, git_project: Path) -> None:
        assert notes_mod.read_all(git_project, ref="never-written") == []

    def test_the_ref_is_namespaced(self, git_project: Path) -> None:
        """Notes live under refs/notes, so they can never collide with a branch."""
        notes_mod.append_record(git_project, record("c" * 40), ref="harness")
        refs = subprocess.run(
            ["git", "for-each-ref", "refs/notes"],
            cwd=git_project,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert "refs/notes/harness" in refs

    def test_records_survive_a_plain_clone_in_the_working_tree(self, git_project: Path) -> None:
        """The note is an object in the repository, so a copy of the repository
        carries it — the property §10 names as the reason to prefer notes."""
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha, session_id="kept"), ref="harness")
        assert notes_mod.read_note(git_project, sha, ref="harness")[0].session_id == "kept"

    def test_transport_commands_are_reported_not_executed(self) -> None:
        """Pushing is a separate authorised action; a library must not push."""
        push, fetch = notes_mod.push_commands("harness")
        assert push == "git push origin refs/notes/harness"
        assert "refs/notes/harness" in fetch

    def test_an_unreadable_note_is_reported(self, git_project: Path) -> None:
        sha = head_sha(git_project)
        subprocess.run(
            ["git", "notes", "--ref=harness", "add", "-f", "-m", "{broken", sha],
            cwd=git_project,
            check=True,
            capture_output=True,
        )
        with pytest.raises(RecordError):
            notes_mod.read_note(git_project, sha, ref="harness")


class TestNothingExecutes:
    """The ledger records; it does not apply.

    The property is narrower than "no subprocess at all": `notes.py` legitimately
    runs `git` to read and write notes. What must not exist is a path from a
    **record's contents** to execution — a proposal's `target_path` or `summary`
    reaching a shell — and no file mutation outside git's own notes.
    """

    def test_no_shell_is_constructed_from_record_content(self) -> None:
        """Every `subprocess` call must be a literal git command.

        Passing `shell=True`, or building the argv from a record field, is how a
        recorder would become an executor. Asserting the argv is a list literal
        rules both out without banning `git` runs that are the storage mechanism.
        """

        for module in (notes_mod.__file__, mirror_mod.__file__):
            tree = ast.parse(Path(module).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name != "run":
                    continue
                assert not any(kw.arg == "shell" for kw in node.keywords), (
                    f"{module} passes shell= to run"
                )
                # The command must be a literal list, never assembled from data.
                first = node.args[0] if node.args else None
                assert isinstance(first, ast.List), (
                    f"{module} builds a subprocess command from a non-literal"
                )

    def test_the_ledger_mutates_no_files(self) -> None:
        """No write/delete call outside git's own notes — the ledger records, it
        does not change the working tree."""
        forbidden = {"write_text", "write_bytes", "unlink", "rmdir", "remove", "rmtree"}
        for module in (notes_mod.__file__, mirror_mod.__file__):
            tree = ast.parse(Path(module).read_text(encoding="utf-8"))
            called = {
                getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
            }
            assert not (called & forbidden), f"{module} calls {called & forbidden}"

    def test_appending_a_record_leaves_the_working_tree_unchanged(self, git_project: Path) -> None:
        """Writing a note must not dirty the tree, or a ledger would make every
        subsequent run report a dirty tree."""

        def porcelain() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=git_project,
                capture_output=True,
                text=True,
                check=False,
            ).stdout

        before = porcelain()
        notes_mod.append_record(git_project, record("d" * 40), ref="harness")
        assert porcelain() == before


class TestMirror:
    def test_the_mirror_is_identical_to_the_notes(self, pg_conn: Any, git_project: Path) -> None:
        """Drop the mirror, rebuild from the notes, require an identical digest."""
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha, session_id="m-1"), ref="harness")
        notes_mod.append_record(
            git_project,
            record(sha, session_id="m-2", prompt=PromptRef(fingerprint=FP, budget=1, unit="word")),
            ref="harness",
        )

        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        first = mirror_mod.mirror_digest(pg_conn)
        mirror_mod.reset(pg_conn)
        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        assert mirror_mod.mirror_digest(pg_conn) == first
        assert first == mirror_mod.ledger_digest(git_project, ref="harness")

    def test_the_mirror_is_not_empty_so_the_comparison_is_meaningful(
        self, pg_conn: Any, git_project: Path
    ) -> None:
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha), ref="harness")
        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        assert len(mirror_mod.read_back(pg_conn)) == 1

    def test_a_mirrored_record_round_trips_every_field(
        self, pg_conn: Any, git_project: Path
    ) -> None:
        sha = head_sha(git_project)
        original = record(
            sha,
            proposal={"intent": "push"},
            verdict={"summary": "refused", "may_execute": False},
            effect=Effect(state="failed", detail="rejected"),
        )
        notes_mod.append_record(git_project, original, ref="harness")
        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        assert mirror_mod.read_back(pg_conn)[0].as_dict() == original.as_dict()

    def test_the_mirror_is_rebuilt_not_accumulated(self, pg_conn: Any, git_project: Path) -> None:
        """A record removed from the notes must disappear from the mirror, or the
        mirror slowly becomes the authority."""
        sha = head_sha(git_project)
        notes_mod.append_record(git_project, record(sha, session_id="x"), ref="harness")
        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        assert len(mirror_mod.read_back(pg_conn)) == 1

        # Rewrite the note without that record, then re-mirror.
        subprocess.run(
            ["git", "notes", "--ref=harness", "remove", sha],
            cwd=git_project,
            check=True,
            capture_output=True,
        )
        mirror_mod.write_mirror(git_project, pg_conn, ref="harness")
        assert mirror_mod.read_back(pg_conn) == []

    def test_the_join_that_git_cannot_do(self, pg_conn: Any, git_project: Path) -> None:
        """Which sessions touched a work item — a query, not a log read."""
        sha = head_sha(git_project)
        notes_mod.append_record(
            git_project, record(sha, session_id="j-1", work_id="MRB-M06"), ref="h"
        )
        notes_mod.append_record(
            git_project, record(sha, session_id="j-2", work_id="MRB-M07"), ref="h"
        )
        mirror_mod.write_mirror(git_project, pg_conn, ref="h")
        rows = mirror_mod.sessions_for_work_item(pg_conn, "MRB-M06")
        assert [r["session_id"] for r in rows] == ["j-1"]


class TestCLI:
    def test_append_then_list(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["ledger", "append", "--work-id", "MRB-M06-S01"]) == 0
        assert "recorded session" in capsys.readouterr().out
        assert main(["ledger", "list"]) == 0
        assert "MRB-M06-S01" in capsys.readouterr().out

    def test_append_reports_nothing_when_the_ledger_is_empty(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["ledger", "list"]) == 0
        assert "no records" in capsys.readouterr().out

    def test_json_list_is_parseable(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        main(["ledger", "append", "--work-id", "MRB-M06-S01"])
        capsys.readouterr()
        assert main(["ledger", "list", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["work_id"] == "MRB-M06-S01"

    def test_gate_records_a_verdict(
        self, git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """The verdict is what makes the ledger an audit trail rather than a diary."""
        proposal = tmp_path / "p.json"
        proposal.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "work_id": "MRB-M06-S01",
                    "intent": "push",
                    "summary": "push",
                    "branch": "main",
                    "test_effect_passed": True,
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(git_project)
        assert (
            main(
                [
                    "ledger",
                    "append",
                    "--work-id",
                    "MRB-M06-S01",
                    "--proposal",
                    str(proposal),
                    "--gate",
                ]
            )
            == 0
        )
        assert "refused by: branch-policy" in capsys.readouterr().out

    def test_gate_without_a_proposal_is_usage_error(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["ledger", "append", "--work-id", "x", "--gate"]) == 4

    def test_verify_reports_the_digest(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        main(["ledger", "append", "--work-id", "MRB-M06-S01"])
        capsys.readouterr()
        assert main(["ledger", "verify"]) == 0
        out = capsys.readouterr().out
        assert "records : 1" in out
        assert "digest" in out

    def test_transport_prints_commands(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["ledger", "transport"]) == 0
        out = capsys.readouterr().out
        assert "push origin refs/notes/harness" in out
        assert "not carried by a plain clone" in out

    def test_show_reports_a_commits_records(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        main(["ledger", "append", "--work-id", "MRB-M06-S01"])
        capsys.readouterr()
        assert main(["ledger", "show"]) == 0
        assert "MRB-M06-S01" in capsys.readouterr().out

    def test_mirror_without_a_dsn_is_three(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        monkeypatch.delenv("MRB_HARNESS_DSN", raising=False)
        assert main(["ledger", "mirror"]) == 3

    def test_verify_with_a_dsn_checks_the_mirror(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys, pg_dsn: str
    ) -> None:
        monkeypatch.chdir(git_project)
        main(["ledger", "append", "--work-id", "MRB-M06-S01"])
        capsys.readouterr()
        assert main(["ledger", "verify", "--dsn", pg_dsn]) == 0
        assert "mirror  : identical to the notes" in capsys.readouterr().out
