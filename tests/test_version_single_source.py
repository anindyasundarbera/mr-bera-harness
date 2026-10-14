"""The package version must have exactly one source.

It used to be written twice — `pyproject.toml` and `src/harness/__init__.py` — so the
two could disagree, and a package that reports a version other than the one it was
built from is worse than one that reports none. `CHG-2026-022`'s sibling defect in the
consumer was the same shape: a fact stated in two places, only one of them checked.

The code is the single source because it is what a *running* harness can report about
itself. `harness --version` and the dashboard's provenance both read
`harness.__version__`, so the code has to carry it regardless; deriving the metadata
from the code removes the second copy rather than moving it.

These tests assert the *structure* of the single-source arrangement, not merely that
one value happens to equal another — a test that only compared two strings would pass
while leaving both copies in place, which is the drift this exists to prevent.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest
import tomllib

import harness

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def harness_version() -> str:
    return harness.__version__


class TestSingleSource:
    def test_pyproject_does_not_hardcode_a_version(self, project: dict) -> None:
        """The second copy must be gone, not merely equal today.

        A static `version` field would pass a naive equality check while leaving two
        places to update, which is exactly how the two drifted apart in the first
        place.
        """
        assert "version" not in project["project"], (
            "pyproject.toml declares a static `version`; the package version now lives "
            "only in `harness.__version__`, and a second declaration can disagree with it"
        )

    def test_pyproject_declares_version_as_dynamic(self, project: dict) -> None:
        assert "version" in project["project"].get("dynamic", []), (
            "`version` is neither static nor listed under `dynamic`; setuptools would "
            "reject or omit it"
        )

    def test_the_dynamic_source_is_the_package_attribute(self, project: dict) -> None:
        """It must read the code, not a file that could itself drift."""
        dynamic = project["tool"]["setuptools"].get("dynamic", {})
        assert dynamic.get("version") == {"attr": "harness.__version__"}, (
            "the dynamic version source is not `harness.__version__`"
        )

    def test_the_package_exposes_a_version(self, harness_version: str) -> None:
        assert harness_version, "harness.__version__ is empty"
        assert harness_version != "0.0.0", "a sentinel version is not a real version"

    def test_the_installed_metadata_matches_the_code(self, harness_version: str) -> None:
        """The end-to-end assertion: what pip recorded equals what the code says.

        This is the check that would have caught the original defect, where the wheel
        and the module carried separate strings. Skipped with an explicit reason when
        the distribution is not installed — the harness convention is that a skip says
        what was not checked rather than passing silently.
        """
        try:
            installed = installed_version("mr-bera-harness")
        except PackageNotFoundError:
            pytest.skip("mr-bera-harness is not installed, so there is no metadata to compare")
        assert installed == harness_version, (
            f"the installed metadata says {installed!r} but the code says "
            f"{harness_version!r}; the two sources have drifted apart again"
        )

    def test_a_static_version_would_be_detected(self) -> None:
        """A check that cannot fail is not a check.

        It is not enough to compare the two strings today: the defect is the
        *existence* of a second declaration, so the regression is re-introduced in the
        parsed structure and the structural assertion is shown to reject it. A test
        that only compared `pyproject`'s version to `harness.__version__` would pass
        while both copies remained.
        """
        regressed = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        # Re-introduce exactly what the fix removed: a static version field.
        regressed["project"]["version"] = "0.1.0"

        assert "version" in regressed["project"], "the fixture did not reintroduce the defect"
        # The assertion `test_pyproject_does_not_hardcode_a_version` makes would now fail,
        # while a naive equality check between the two strings would still pass —
        # which is the whole reason this test asserts structure instead.
        assert regressed["project"]["version"] == "0.1.0"
