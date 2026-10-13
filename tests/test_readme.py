"""Tests for README.md — the first document a reader meets.

The README links to the documents it describes, and a link that does not resolve is
the cheapest possible drift: the reader is told where the truth is and finds nothing
there. This happened once already — `README.md` pointed at
`docs/HARNESS_ARCHITECTURE.md` while the file lived at `docs/design/` — and unlike the
repository's other artifacts, the README is checked by nothing: `harness doctor`
covers the OKF bundle, the routing invariants and the entries, not this file.

Stated plainly, because a check that claims more than it does is the failure mode
this repository exists to prevent: **these tests prove a link resolves, not that the
document it names still says what the README says it says.** The stale claim that
prompted this file — a closed gap still described as open — is not machine-checkable
from a link, and nothing here pretends otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

# `[text](target)` and `![alt](target)`. The target stops at the first `)` or space,
# so an optional title (`(path "title")`) cannot swallow the path.
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(?P<target>[^)\s]+)")

# A path in backticks, but only when it looks like an in-tree file: a known extension
# and an in-tree top-level directory. `harness.toml` in a consumer example, prose in
# backticks and globs all have to fall through, or the test invents failures.
_BACKTICKED_PATH = re.compile(
    r"`(?P<path>(?:docs|knowledge|src|tests|scripts)/[A-Za-z0-9_./-]+\.(?:md|toml|yml|yaml|py))`"
)


def relative_targets(readme: Path) -> list[tuple[int, str]]:
    """Every relative link target in `readme`, with its line number.

    Fenced code blocks are skipped: a README example writes a *consumer's*
    `harness.toml`, which need not exist in this repository, and checking it would be
    the test lying about what the repository contains.
    """
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _MARKDOWN_LINK.finditer(line):
            target = match.group("target")
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            found.append((number, target.split("#", 1)[0]))
        for match in _BACKTICKED_PATH.finditer(line):
            found.append((number, match.group("path")))
    return found


def broken_targets(readme: Path, root: Path) -> list[tuple[int, str]]:
    return [(n, t) for n, t in relative_targets(readme) if t and not (root / t).exists()]


class TestReadmeLinks:
    def test_readme_exists(self) -> None:
        assert README.is_file(), "the README is what this module checks"

    def test_every_relative_link_resolves(self) -> None:
        """A README that points nowhere sends the reader away from the truth."""
        broken = broken_targets(README, REPO_ROOT)
        assert not broken, "the README links to paths that do not exist: " + ", ".join(
            f"line {n} -> {t}" for n, t in broken
        )

    def test_the_check_can_fail(self, tmp_path: Path) -> None:
        """A check that cannot fail is not a check.

        Pointed at a README whose only link is to a file that is not there, it must
        report it. Without this, a typo in the regex would leave the suite green while
        checking nothing.
        """
        broken = tmp_path / "README.md"
        broken.write_text("see [the design](docs/does-not-exist.md)\n", encoding="utf-8")
        assert relative_targets(broken) == [(1, "docs/does-not-exist.md")]
        assert broken_targets(broken, tmp_path) == [(1, "docs/does-not-exist.md")]

    def test_a_resolvable_link_passes(self, tmp_path: Path) -> None:
        """The other half of the pair: a link that resolves must not be reported."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "DESIGN.md").write_text("x", encoding="utf-8")
        good = tmp_path / "README.md"
        good.write_text("see [the design](docs/DESIGN.md)\n", encoding="utf-8")
        assert broken_targets(good, tmp_path) == []

    def test_a_fenced_example_is_not_a_link(self, tmp_path: Path) -> None:
        """A consumer's `harness.toml` in an example must not be read as this repo's."""
        example = tmp_path / "README.md"
        example.write_text(
            "```toml\npath = `docs/not-here.md`\n```\n\nsee `docs/DESIGN.md`\n",
            encoding="utf-8",
        )
        assert relative_targets(example) == [(5, "docs/DESIGN.md")]

    def test_absolute_and_anchor_links_are_ignored(self, tmp_path: Path) -> None:
        """Only in-tree paths are this repository's to resolve."""
        external = tmp_path / "README.md"
        external.write_text(
            "[spec](https://example.com/x.md) [top](#install) [mail](mailto:a@b.c)\n",
            encoding="utf-8",
        )
        assert relative_targets(external) == []
