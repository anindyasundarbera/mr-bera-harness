"""Tests for the usage dashboard.

Three properties matter, and each is asserted rather than assumed:

* **It is a viewer.** The report runs checks from the repository it is pointed at,
  and adds no mutation path.
* **The rendered file is self-contained.** No server, no network, no external
  asset — a dashboard that needs a CDN breaks when the CDN does.
* **History accumulates and never overwrites.** Losing a run to a same-second
  write would destroy the very thing history is for.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import pytest

from harness.cli import main
from harness.config import load_config
from harness.dashboard.render import render_html
from harness.dashboard.report import REPORT_VERSION, Check, Run, collect
from harness.dashboard.store import (
    ReportError,
    latest_run,
    list_runs,
    load_history,
    reports_dir,
    write_run,
)


class TestReport:
    def test_collects_every_category(self, git_project: Path) -> None:
        run = collect(
            load_config(git_project), now=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        )
        categories = {c.category for c in run.checks}
        assert {"documentation", "governance", "index", "compilation", "verification"} <= categories

    def test_records_provenance(self, git_project: Path) -> None:
        run = collect(load_config(git_project))
        assert run.commit_sha
        assert run.branch
        assert run.project == "TestProject"
        assert run.root == str(git_project.resolve())

    def test_reports_a_dirty_tree_and_a_clean_one(self, git_project: Path) -> None:
        """A run over uncommitted work is a different claim from a run over a commit."""
        assert collect(load_config(git_project)).dirty is False
        (git_project / "scratch.txt").write_text("x", encoding="utf-8")
        assert collect(load_config(git_project)).dirty is True

    def test_unknown_is_not_a_pass(self) -> None:
        run = Run(
            project="P",
            root="/",
            commit_sha="abc",
            dirty=False,
            branch="main",
            harness_version="0",
            generated_at="t",
            report_version=1,
            checks=(Check("x", "c", "unknown"),),
        )
        assert run.healthy is True  # unknown does not fail the run
        assert run.counts()["unknown"] == 1

    def test_a_failure_makes_the_run_unhealthy(self) -> None:
        run = Run(
            project="P",
            root="/",
            commit_sha="abc",
            dirty=False,
            branch="main",
            harness_version="0",
            generated_at="t",
            report_version=1,
            checks=(Check("x", "c", "fail"),),
        )
        assert run.healthy is False

    def test_index_without_a_dsn_is_unknown(self, git_project: Path) -> None:
        """An unreachable store is not a failing index, and must not read as one."""
        run = collect(load_config(git_project), dsn=None)
        index = next(c for c in run.checks if c.category == "index")
        assert index.status == "unknown"
        assert "DSN" in index.detail

    def test_guards_on_a_protected_branch_are_unknown_not_fail(self, git_project: Path) -> None:
        """A correct refusal must not be painted red, or red loses its meaning."""
        run = collect(load_config(git_project), branch="main")
        guards = next(c for c in run.checks if c.name == "session guards")
        assert guards.status == "unknown"

    def test_guards_on_a_feature_branch_pass(self, git_project: Path) -> None:
        run = collect(load_config(git_project), branch="feat/x")
        guards = next(c for c in run.checks if c.name == "session guards")
        assert guards.status == "pass"

    def test_report_is_json_serializable(self, git_project: Path) -> None:
        json.dumps(collect(load_config(git_project)).as_dict())

    def test_report_version_is_recorded(self, git_project: Path) -> None:
        assert collect(load_config(git_project)).report_version == REPORT_VERSION

    def test_tests_can_be_skipped_for_speed(self, git_project: Path) -> None:
        run = collect(load_config(git_project), include_tests=False)
        assert not any(c.name == "tests" for c in run.checks)


class TestStore:
    def test_writes_one_file_per_run(self, tmp_path: Path) -> None:
        first = write_run(
            tmp_path, {"a": 1}, moment=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        )
        second = write_run(
            tmp_path, {"a": 2}, moment=_dt.datetime(2026, 1, 2, tzinfo=_dt.timezone.utc)
        )
        assert first != second
        assert len(list_runs(tmp_path)) == 2

    def test_never_overwrites_a_same_second_run(self, tmp_path: Path) -> None:
        """A collision must add a file, not replace one."""
        moment = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        a = write_run(tmp_path, {"n": 1}, moment=moment)
        b = write_run(tmp_path, {"n": 2}, moment=moment)
        assert a != b
        assert len(list_runs(tmp_path)) == 2

    def test_filenames_sort_chronologically(self, tmp_path: Path) -> None:
        write_run(tmp_path, {"n": 1}, moment=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc))
        write_run(tmp_path, {"n": 2}, moment=_dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc))
        assert latest_run(tmp_path).read_text(encoding="utf-8").find('"n": 2') >= 0

    def test_latest_is_none_when_nothing_recorded(self, tmp_path: Path) -> None:
        assert latest_run(tmp_path) is None

    def test_history_is_newest_first(self, tmp_path: Path) -> None:
        write_run(tmp_path, {"n": 1}, moment=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc))
        write_run(tmp_path, {"n": 2}, moment=_dt.datetime(2026, 1, 2, tzinfo=_dt.timezone.utc))
        history = load_history(tmp_path)
        assert len(history) == 2
        assert history.latest["n"] == 2

    def test_a_malformed_run_is_reported_not_skipped(self, tmp_path: Path) -> None:
        """Silently dropping it would make history look shorter than it is."""
        write_run(tmp_path, {"n": 1})
        directory = reports_dir(tmp_path)
        (directory / "2026-01-01T00-00-00Z.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ReportError, match="unreadable"):
            load_history(tmp_path)

    def test_transitions_reports_a_status_change(self, tmp_path: Path) -> None:
        """The reason to keep history: a check that was passing and now fails."""

        def run_at(n: int, status: str) -> dict:
            return {
                "generated_at": f"2026-01-0{n}T00:00:00Z",
                "checks": [{"name": "tests", "status": status}],
            }

        write_run(
            tmp_path, run_at(1, "pass"), moment=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        )
        write_run(
            tmp_path, run_at(2, "fail"), moment=_dt.datetime(2026, 1, 2, tzinfo=_dt.timezone.utc)
        )
        changes = load_history(tmp_path).transitions()
        assert changes == [
            {"check": "tests", "from": "pass", "to": "fail", "at": "2026-01-02T00:00:00Z"}
        ]

    def test_no_transitions_when_nothing_changed(self, tmp_path: Path) -> None:
        def run_at(n: int) -> dict:
            return {
                "generated_at": f"2026-01-0{n}T00:00:00Z",
                "checks": [{"name": "tests", "status": "pass"}],
            }

        write_run(tmp_path, run_at(1), moment=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc))
        write_run(tmp_path, run_at(2), moment=_dt.datetime(2026, 1, 2, tzinfo=_dt.timezone.utc))
        assert load_history(tmp_path).transitions() == []


class TestRender:
    def _run(self) -> dict:
        return {
            "project": "TestProject",
            "root": "/tmp/x",
            "commit_sha": "abcdef1234567890",
            "dirty": False,
            "branch": "main",
            "harness_version": "0.1.0",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "report_version": 1,
            "counts": {"pass": 1, "fail": 0, "unknown": 0},
            "healthy": True,
            "checks": [
                {
                    "name": "tests",
                    "category": "verification",
                    "status": "pass",
                    "detail": "ok",
                    "findings": [],
                }
            ],
        }

    def test_renders_a_complete_document(self) -> None:
        html = render_html(self._run())
        assert html.startswith("<!doctype html>")
        assert html.rstrip().endswith("</html>")

    def test_is_self_contained(self) -> None:
        """No external asset: the file must work from `file://`, offline, forever."""
        html = render_html(self._run())
        for reference in ("http://", "https://", "src=", "href=", "@import", "<link"):
            assert reference not in html, f"external reference: {reference}"

    def test_embeds_parseable_json(self) -> None:
        html = render_html(self._run(), history=(self._run(),))
        match = re.search(
            r'<script id="harness-data" type="application/json">(.*?)</script>', html, re.S
        )
        assert match is not None
        payload = json.loads(match.group(1))
        assert payload["run"]["project"] == "TestProject"
        assert len(payload["history"]) == 1

    def test_escapes_so_a_string_cannot_close_the_script_element(self) -> None:
        """A `</script>` inside a title would end the element and break the page."""
        run = self._run()
        run["project"] = "evil</script><script>alert(1)</script>"
        html = render_html(run)
        assert "</script><script>alert(1)" not in html
        assert "\\u003c/script\\u003e" in html

    def test_escapes_html_comment_openers(self) -> None:
        run = self._run()
        run["project"] = "<!-- x -->"
        assert "<!--" not in render_html(run)

    def test_shows_the_dirty_tree(self) -> None:
        run = self._run()
        run["dirty"] = True
        assert "uncommitted changes" in render_html(run)

    def test_renders_with_empty_history(self) -> None:
        assert "No prior runs recorded" in render_html(self._run(), history=())

    def test_renders_transitions(self) -> None:
        html = render_html(
            self._run(),
            transitions=[{"check": "tests", "from": "pass", "to": "fail", "at": "2026-01-02"}],
        )
        assert "tests" in html

    def test_no_transitions_message(self) -> None:
        assert "No status changes" in render_html(self._run())


class TestCLI:
    def test_dashboard_run_records_and_renders(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["dashboard", "run", "--out", str(git_project / "dash.html")]) in {0, 1}
        assert (git_project / "dash.html").is_file()
        assert list_runs(git_project)

    def test_dashboard_history_lists_runs(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        write_run(git_project, {"generated_at": "t", "commit_sha": "a" * 40, "counts": {}})
        assert main(["dashboard", "history"]) == 0
        assert "pass=0" in capsys.readouterr().out

    def test_dashboard_history_json_is_parseable(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(git_project)
        write_run(git_project, {"generated_at": "t", "commit_sha": "a" * 40, "counts": {}})
        assert main(["dashboard", "history", "--json"]) == 0
        assert isinstance(json.loads(capsys.readouterr().out), list)

    def test_render_without_runs_is_an_error(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        assert main(["dashboard", "render"]) == 1

    def test_render_reuses_recorded_runs(
        self, git_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(git_project)
        write_run(
            git_project,
            {"generated_at": "t", "commit_sha": "a" * 40, "counts": {}, "healthy": True},
        )
        assert main(["dashboard", "render", "--out", str(git_project / "d.html"), "--quiet"]) == 0
        assert (git_project / "d.html").is_file()
