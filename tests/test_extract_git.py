"""Tests for the git source: provenance, and purity against the working tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import git_commit
from harness.config import load_config
from harness.extract.model import model_digest
from harness.extract.source import IndexSourceError, commit_sha, materialize_commit, model_from_git


class TestProvenance:
    def test_model_records_the_commit_it_came_from(self, git_project: Path) -> None:
        config = load_config(git_project)
        model = model_from_git(git_project, config)
        assert model.commit_sha == commit_sha(git_project)
        assert model.project == config.identity.name
        assert model.source_rev == "HEAD"

    def test_unknown_revision_fails_loudly(self, git_project: Path) -> None:
        with pytest.raises(IndexSourceError, match="cannot resolve"):
            commit_sha(git_project, "does-not-exist")

    def test_not_a_repository_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(IndexSourceError):
            commit_sha(tmp_path)


class TestCommittedBytesOnly:
    def test_uncommitted_edits_are_invisible(self, git_project: Path) -> None:
        """An uncommitted edit must not reach the index.

        If the working tree leaked into extraction, the index would encode a fact
        git does not hold.
        """
        config = load_config(git_project)
        before = model_digest(model_from_git(git_project, config))

        target = git_project / "knowledge" / "modules" / "M06-engine.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\n## Uncommitted\n", encoding="utf-8"
        )

        assert model_digest(model_from_git(git_project, config)) == before

    def test_untracked_files_are_invisible(self, git_project: Path) -> None:
        config = load_config(git_project)
        before = model_digest(model_from_git(git_project, config))
        (git_project / "knowledge" / "modules" / "untracked.md").write_text(
            "---\ntype: Concept\nmodule: MRB-M06\ncovers: [MRB-M06]\n---\n\nBody.\n",
            encoding="utf-8",
        )
        assert model_digest(model_from_git(git_project, config)) == before

    def test_committing_the_edit_changes_the_digest(self, git_project: Path) -> None:
        """The inverse: the invariant is not vacuous."""
        config = load_config(git_project)
        before = model_digest(model_from_git(git_project, config))

        target = git_project / "knowledge" / "modules" / "M06-engine.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\n## Committed\n", encoding="utf-8"
        )
        git_commit(git_project, "docs: change")

        assert model_digest(model_from_git(git_project, config)) != before

    def test_pinned_revision_is_reproducible(self, git_project: Path) -> None:
        config = load_config(git_project)
        first = commit_sha(git_project)
        assert model_digest(model_from_git(git_project, config, rev=first)) == model_digest(
            model_from_git(git_project, config, rev=first)
        )


class TestMaterialize:
    def test_materialized_tree_contains_only_tracked_files(self, git_project: Path) -> None:
        (git_project / "junk.tmp").write_text("x", encoding="utf-8")
        with materialize_commit(git_project) as tree:
            assert (tree / "harness.toml").is_file()
            assert not (tree / "junk.tmp").exists()
            assert (tree / "knowledge" / "modules" / "M06-engine.md").is_file()


class TestRegistries:
    def test_declared_registry_is_read_from_the_tree(self, git_project: Path) -> None:
        """Registries come from `harness.toml`; the harness never guesses them."""
        model = model_from_git(git_project, load_config(git_project))
        assert len(model.registry_tables) == 1
        table = model.registry_tables[0]
        assert table.source == "docs/GAP_REGISTER.md"
        assert table.columns == ("Gap ID", "State", "Note")
        assert table.rows[0]["Gap ID"] == "GAP-CTL-001"
        assert table.rows[1]["State"] == "BlockedOwner"

    def test_undeclared_registry_is_not_read(self, git_project: Path) -> None:
        """A file that is not declared as a registry is never parsed as one."""
        (git_project / "docs" / "NOT_A_REGISTER.md").write_text(
            "| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8"
        )
        git_commit(git_project, "docs: extra")
        model = model_from_git(git_project, load_config(git_project))
        assert [t.source for t in model.registry_tables] == ["docs/GAP_REGISTER.md"]
