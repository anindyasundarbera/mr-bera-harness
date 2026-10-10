"""Tests for harness.entries.commits — Conventional Commits 1.0.0.

Enforced in code because a convention an agent must remember is one it will
eventually forget.
"""

from __future__ import annotations

import pytest

from harness.entries.commits import TYPES, check, commits_in_range, default_range


class TestValidMessages:
    @pytest.mark.parametrize(
        "subject",
        [
            "feat: add a thing",
            "fix: correct a thing",
            "docs: explain a thing",
            "chore: tidy a thing",
            "ci: change a pipeline",
            "refactor: reshape a thing",
            "test: cover a thing",
            "perf: speed up a thing",
            "build: adjust packaging",
            "style: reformat a thing",
            "revert: undo a thing",
            "feat(parser): add ability to parse arrays",
            "feat!: send an email when a product is shipped",
            "fix(api)!: drop support for an old client",
        ],
    )
    def test_accepted(self, subject: str) -> None:
        assert check(subject) == []

    def test_every_declared_type_is_accepted(self) -> None:
        for t in sorted(TYPES):
            assert check(f"{t}: do the thing") == [], t


class TestRejectedMessages:
    @pytest.mark.parametrize(
        "subject",
        [
            "added a thing",
            "feat add a thing",
            "feat:no space",
            "feature: unknown type",
            "Feat: capitalised type",
            "feat: Ends with a period.",
            "feat: Starts uppercase",
        ],
    )
    def test_rejected(self, subject: str) -> None:
        assert check(subject), f"{subject!r} should be rejected"

    def test_overlong_subject_rejected(self) -> None:
        assert check("feat: " + "x" * 200)

    def test_empty_breaking_footer_rejected(self) -> None:
        assert check("feat!: break it", "BREAKING CHANGE:") is not None

    def test_breaking_footer_with_content_accepted(self) -> None:
        assert check("feat!: break it", "BREAKING CHANGE: the key moved") == []


class TestSpecNuance:
    def test_bang_alone_is_conformant(self) -> None:
        """Per the spec, `!` OR a footer marks a break. Demanding both rejects
        valid commits, which this checker once did."""
        assert check("feat!: break it") == []


class TestExemptMessages:
    def test_merge_commit_exempt(self) -> None:
        assert check("Merge pull request #3 from x/y") == []
        assert check("Merge branch 'main' into feat/x") == []

    def test_github_pr_merge_commit_exempt(self) -> None:
        """GitHub checks out a pull request at a synthetic merge commit."""
        first = "16d5c09abc1234567890abcdef0123456789abcd"
        second = "def4567890abcdef0123456789abcdef01234567"
        assert check(f"Merge {first} into {second}") == []

    def test_non_merge_descriptions_not_exempt(self) -> None:
        """Broadening the exemption must not exempt real commits."""
        assert check("Mergeability improved")
        assert check("Merge conflicts resolved")


class TestCli:
    """The harness has one entry point; these exercise it, not a per-module main."""

    def test_check_is_what_the_cli_calls(self) -> None:
        assert check("feat: add a thing") == []
        assert check("nope")


class TestRangeHandling:
    """Range resolution, including the shallow-checkout case that broke CI once."""

    def test_default_range_is_resolvable(self) -> None:
        """The range must resolve, whatever branch we are on.

        On the default branch there is legitimately nothing to compare, so an
        empty result is valid; an *unresolvable* range is not, because that is
        the shallow-checkout failure that once broke CI.
        """

        rev_range = default_range()
        assert rev_range
        assert isinstance(commits_in_range(rev_range), list)

    def test_unresolvable_range_explains_itself(self) -> None:
        """A shallow clone must produce guidance, not raw git output."""

        with pytest.raises(SystemExit) as exc:
            commits_in_range("nonexistent-ref-xyz..HEAD")
        message = str(exc.value)
        assert "cannot resolve commit range" in message
        assert "shallow" in message.lower()

    def test_single_commit_always_resolves(self) -> None:
        """`HEAD` works however shallow the checkout; `HEAD~1..HEAD` does not."""

        commits = commits_in_range("HEAD")
        assert commits
        sha, subject, _body = commits[0]
        assert len(sha) >= 7
        assert subject
