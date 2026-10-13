"""The rebuild invariant: drop the database, rebuild from git, prove it is identical.

This is the test that stops PostgreSQL from silently becoming a second source of
truth. It has two halves, and both are required:

* the rebuild must produce an *identical* index, and
* the comparison must be capable of failing.

A test that only ever compared two empty models would pass while proving nothing,
so this module also pins a non-empty model and a mutation that must change the
digest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import git_commit
from harness.config import load_config
from harness.extract.model import model_digest
from harness.extract.source import model_from_git
from harness.index.store import read_model, reset, write_model


def _rebuild(conn: Any, root: Path) -> tuple[str, Any]:
    """Reset the database, rebuild from git, and return (digest, model)."""
    reset(conn)
    model = model_from_git(root, load_config(root))
    write_model(conn, model)
    read = read_model(conn)
    return model_digest(read), read


class TestRebuildInvariant:
    def test_drop_and_rebuild_from_git_is_identical(self, pg_conn: Any, git_project: Path) -> None:
        """Git -> model -> Postgres, destroyed and rebuilt, must be identical."""
        from_git = model_from_git(git_project, load_config(git_project))

        # First build.
        reset(pg_conn)
        write_model(pg_conn, from_git)
        first_digest = model_digest(read_model(pg_conn))

        # Destroy the database entirely, then rebuild from git alone.
        reset(pg_conn)
        reset_again = model_from_git(git_project, load_config(git_project))
        write_model(pg_conn, reset_again)
        second_digest = model_digest(read_model(pg_conn))

        assert first_digest == second_digest
        assert first_digest == model_digest(from_git)

    def test_the_model_is_not_empty_so_the_comparison_is_meaningful(
        self, pg_conn: Any, git_project: Path
    ) -> None:
        model = model_from_git(git_project, load_config(git_project))
        assert model.documents, "an empty model would make the invariant vacuous"
        assert model.registry_tables, "the registry table must round-trip too"
        assert model.commit_sha

    def test_rebuild_is_identical_table_by_table(self, pg_conn: Any, git_project: Path) -> None:
        """A digest could in principle collide; compare the tables too."""
        first_digest, first = _rebuild(pg_conn, git_project)
        second_digest, second = _rebuild(pg_conn, git_project)

        assert first_digest == second_digest
        assert first.documents == second.documents
        assert first.registry_tables == second.registry_tables
        assert first.commit_sha == second.commit_sha

    def test_a_git_change_breaks_the_equality(self, pg_conn: Any, git_project: Path) -> None:
        """Without this, the invariant could hold while indexing nothing."""
        before, _ = _rebuild(pg_conn, git_project)

        target = git_project / "knowledge" / "modules" / "M06-engine.md"
        target.write_text(target.read_text(encoding="utf-8") + "\n\n## New\n", encoding="utf-8")
        git_commit(git_project, "docs: change")

        after, _ = _rebuild(pg_conn, git_project)
        assert before != after

    def test_the_index_does_not_drift_from_git(self, pg_conn: Any, git_project: Path) -> None:
        """Rebuilding from git always yields exactly the committed content."""
        target = git_project / "knowledge" / "modules" / "M06-orchestration.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n\n## Uncommitted only\n", encoding="utf-8"
        )
        digest, read = _rebuild(pg_conn, git_project)
        headings = {d.concept_id: d.headings for d in read.documents}
        assert "Uncommitted only" not in headings.get("modules/M06-orchestration", ())
        assert digest == model_digest(model_from_git(git_project, load_config(git_project)))
