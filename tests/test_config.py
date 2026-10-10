"""Tests for harness.config — the layer that makes the harness project-agnostic."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import HARNESS_TOML
from harness.config import CONFIG_FILENAME, Config, ConfigError, Identity, describe, load_config


class TestDefaults:
    def test_missing_config_falls_back(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert config.configured is False
        assert config.root == tmp_path.resolve()

    def test_missing_config_can_be_required(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="no harness.toml"):
            load_config(tmp_path, required=True)

    def test_defaults_are_usable(self) -> None:
        config = Config.defaults(Path("/tmp"))
        assert config.identity.id_prefix
        assert config.path("docs")


class TestLoading:
    def test_reads_the_configured_project(self, project: Path) -> None:
        config = load_config(project, required=True)
        assert config.configured is True
        assert config.identity.name == "TestProject"
        assert config.identity.id_prefix == "MRB"
        assert config.source == project / CONFIG_FILENAME

    def test_reads_registries(self, project: Path) -> None:
        config = load_config(project)
        assert "gaps" in config.registries
        assert config.registries["gaps"].path == "docs/GAP_REGISTER.md"

    def test_reads_guards_and_commit_types(self, project: Path) -> None:
        config = load_config(project)
        assert "feat" in config.branch_prefixes
        assert config.protected_branches == ("main", "master")
        assert "feat" in config.commit_types

    def test_invalid_toml_raises(self, project: Path) -> None:
        (project / CONFIG_FILENAME).write_text("this is not = = toml", encoding="utf-8")
        with pytest.raises(ConfigError, match="not valid TOML"):
            load_config(project)

    def test_mismatched_levels_and_widths_raises(self, project: Path) -> None:
        (project / CONFIG_FILENAME).write_text(
            '[identity]\nlevels = ["M", "S", "C"]\nwidths = [2, 2]\n', encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="must correspond"):
            load_config(project)

    def test_registry_without_path_raises(self, project: Path) -> None:
        (project / CONFIG_FILENAME).write_text(
            "[registries.bad]\nid_column = 'x'\n", encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="must be a table with a `path`"):
            load_config(project)

    def test_unknown_path_keys_are_ignored(self, project: Path) -> None:
        """A project may add its own path keys without breaking the harness."""
        text = HARNESS_TOML + '\nunknown_path = "ignored"\n'
        (project / CONFIG_FILENAME).write_text(text, encoding="utf-8")
        config = load_config(project)
        assert config.paths.docs == "docs"


class TestIdentityGrammar:
    def test_grammar_accepts_every_valid_depth(self) -> None:
        pattern = Identity().id_pattern()
        for value in (
            "MRB-M06",
            "MRB-M06-S07",
            "MRB-M06-S07-C03",
            "MRB-M06-S07-C03-W01",
            "MRB-M06-S07-C03-W01-A02",
        ):
            assert pattern.match(value), value

    def test_grammar_rejects_malformed(self) -> None:
        pattern = Identity().id_pattern()
        for value in (
            "",
            "MRB",
            "MRB-X",
            "MRB-M6",
            "MRB-M06-S7",
            "NOPE-M06",
            "MRB-M06-S07-C03-W01-A02-X",
        ):
            assert not pattern.match(value), value

    def test_grammar_is_derived_from_configuration(self) -> None:
        """A project numbering differently must still route."""
        identity = Identity(id_prefix="TASK", levels=("P", "T"), widths=(3, 4))
        pattern = identity.id_pattern()
        assert pattern.match("TASK-P001")
        assert pattern.match("TASK-P001-T0002")
        assert not pattern.match("TASK-P01")


class TestPathResolution:
    def test_paths_are_relative_to_root(self, project: Path) -> None:
        config = load_config(project)
        assert config.path("docs") == project / "docs"
        assert config.path("knowledge") == project / "knowledge"
        assert config.path("changelog") == project / "knowledge/changelog"

    def test_paths_can_be_overridden(self, tmp_path: Path) -> None:
        root = tmp_path / "p"
        root.mkdir()
        (root / CONFIG_FILENAME).write_text('[paths]\ndocs = "documentation"\n', encoding="utf-8")
        config = load_config(root)
        assert config.path("docs") == root / "documentation"


class TestDescribe:
    def test_describe_reports_the_source(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        describe(load_config(project))
        out = capsys.readouterr().out
        assert "harness.toml" in out
        assert "TestProject" in out

    def test_describe_says_when_defaults_are_used(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        describe(load_config(tmp_path))
        assert "none found" in capsys.readouterr().out
