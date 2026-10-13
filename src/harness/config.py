"""Harness configuration.

This module is what makes the harness usable by a repository other than MrBera.
Everything project-specific — document locations, identifier grammar, registry
filenames, state-ownership keys, commit scopes — is read from `harness.toml`
rather than hardcoded.

A repository without `harness.toml` gets `Config.defaults()`, which is a
deliberately minimal shape: it will run, and it will report that nothing is
configured rather than silently inventing a location.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

CONFIG_FILENAME = "harness.toml"

# Subdirectories the harness must never treat as concept documents. Mirrors OKF
# SPEC section 3.1 plus the harness's own bookkeeping.
RESERVED_FILENAMES = frozenset({"index.md", "log.md"})


class ConfigError(Exception):
    """Raised when harness.toml is present but unusable."""


@dataclass(frozen=True)
class Identity:
    """How this project names things."""

    name: str = "unnamed-project"
    #: Prefix of every work identifier, e.g. "MRB" for MRB-M06-S07.
    id_prefix: str = "MRB"
    #: Ordered level markers, e.g. ["M", "S", "C", "W", "A"].
    levels: tuple[str, ...] = ("M", "S", "C", "W", "A")
    #: Digits per level, e.g. [2, 2, 2, 2, 2] for MRB-M06-S07-C03-W01-A02.
    widths: tuple[int, ...] = (2, 2, 2, 2, 2)

    def id_pattern(self) -> re.Pattern[str]:
        """Compile the identifier grammar from the configured levels.

        Each optional group nests, so `MRB-M06` and `MRB-M06-S07-C03` both match
        while `MRB-X` and `MRB-M06-S7` do not. Enforcing the whole grammar rather
        than a prefix check is what stops a malformed identifier silently routing
        to a coarser parent chain.
        """
        # Each level is required *relative to its parent*, so MRB-M06 is valid,
        # MRB-M06-S07 is valid, and MRB-M06-S07-C03 is valid, but a level cannot
        # be skipped. Nesting builds that cumulative requirement.
        #
        # The prefix alone is rejected: MRB names a system, not a unit of work,
        # and would route to an empty parent chain.
        levels = [
            rf"(?:-{re.escape(m)}\d{{{w}}})" for m, w in zip(self.levels, self.widths, strict=False)
        ]
        body = ""
        for level in reversed(levels[1:]):
            body = f"(?:{level}{body})?"
        return re.compile(rf"\A{re.escape(self.id_prefix)}{levels[0]}{body}\Z")


@dataclass(frozen=True)
class Paths:
    """Where this project keeps its documents."""

    docs: str = "docs"
    knowledge: str = "knowledge"
    changelog: str = "knowledge/changelog"
    decisions: str = "knowledge/decisions"
    tests: str = "tests"
    tools: str = "tools"


@dataclass(frozen=True)
class Registry:
    """A file the harness reads but never writes."""

    path: str
    #: Column names the harness looks for when parsing a markdown table.
    id_column: str = "id"
    state_column: str = "state"


@dataclass(frozen=True)
class Config:
    """Everything project-specific, in one place."""

    identity: Identity = field(default_factory=Identity)
    paths: Paths = field(default_factory=Paths)
    registries: dict[str, Registry] = field(default_factory=dict)
    #: Allowed branch prefixes for a feature branch.
    branch_prefixes: tuple[str, ...] = (
        "feat",
        "fix",
        "docs",
        "chore",
        "refactor",
        "test",
        "ci",
        "integration",
    )
    #: Branches a coding agent must never commit or push to.
    protected_branches: tuple[str, ...] = ("main", "master")
    #: Glob patterns for paths that must never be tracked.
    forbidden_path_globs: tuple[str, ...] = (
        r"(^|/)\.env(?!\.example(\.|$))(\.|$)",
        r"\.(pem|key|p12|pfx|jks|keystore)$",
        r"(^|/)(credentials|secrets)\.(json|ya?ml)$",
    )
    #: Commit types accepted by the convention check.
    commit_types: tuple[str, ...] = (
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
    )
    #: Root of the consuming repository.
    root: Path = field(default_factory=Path.cwd)
    #: Where harness.toml was found, or None when defaults are in use.
    source: Path | None = None

    @property
    def configured(self) -> bool:
        """False when no harness.toml was found, so callers can say so plainly."""
        return self.source is not None

    def path(self, key: str) -> Path:
        """Resolve a configured path key against the project root."""
        value = getattr(self.paths, key, None)
        if value is None:
            raise ConfigError(f"unknown path key `{key}`")
        return self.root / str(value)

    @classmethod
    def defaults(cls, root: Path | None = None) -> Config:
        return cls(root=(root or Path.cwd()).resolve())


def _tuple_of_str(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"expected a list of strings, got {value!r}")
    return tuple(value)


def load_config(root: Path | None = None, *, required: bool = False) -> Config:
    """Load `harness.toml` from `root`, falling back to defaults.

    `required=True` raises rather than falling back, for callers that must not
    silently operate on an unconfigured project.
    """
    root = (root or Path.cwd()).resolve()
    config_path = root / CONFIG_FILENAME

    if not config_path.is_file():
        if required:
            raise ConfigError(
                f"no {CONFIG_FILENAME} in {root}. The harness needs one to know "
                "where documents and registries live."
            )
        return Config.defaults(root)

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid TOML: {exc}") from exc

    identity_data = data.get("identity", {})
    paths_data = data.get("paths", {})
    guards_data = data.get("guards", {})
    commits_data = data.get("commits", {})

    base = Identity()
    identity = Identity(
        name=str(identity_data.get("name", base.name)),
        id_prefix=str(identity_data.get("id_prefix", base.id_prefix)),
        levels=_tuple_of_str(identity_data.get("levels"), base.levels),
        widths=tuple(int(w) for w in identity_data.get("widths", list(base.widths))),
    )
    if len(identity.levels) != len(identity.widths):
        raise ConfigError(
            f"identity.levels has {len(identity.levels)} entries but identity.widths "
            f"has {len(identity.widths)}; they must correspond"
        )

    base_paths = Paths()
    paths = Paths(**{k: str(v) for k, v in paths_data.items() if hasattr(base_paths, k)})

    registries: dict[str, Registry] = {}
    for name, entry in (data.get("registries") or {}).items():
        if not isinstance(entry, dict) or "path" not in entry:
            raise ConfigError(f"registries.{name} must be a table with a `path`")
        registries[name] = Registry(
            path=str(entry["path"]),
            id_column=str(entry.get("id_column", name)),
            state_column=str(entry.get("state_column", "state")),
        )

    base_guards = Config.defaults(root)
    return Config(
        identity=identity,
        paths=paths,
        registries=registries,
        branch_prefixes=_tuple_of_str(
            guards_data.get("branch_prefixes"), base_guards.branch_prefixes
        ),
        protected_branches=_tuple_of_str(
            guards_data.get("protected_branches"), base_guards.protected_branches
        ),
        forbidden_path_globs=_tuple_of_str(
            guards_data.get("forbidden_path_globs"), base_guards.forbidden_path_globs
        ),
        commit_types=_tuple_of_str(commits_data.get("types"), base_guards.commit_types),
        root=root,
        source=config_path,
    )


def describe(config: Config, stream: Any = None) -> None:
    """Print what the harness understood, so a misconfiguration is visible."""
    out = stream or sys.stdout
    print(f"harness config: {config.source or '(defaults; none found)'}", file=out)
    print(f"  project      : {config.identity.name}", file=out)
    print(f"  id grammar   : {config.identity.id_pattern().pattern}", file=out)
    print(f"  docs         : {config.path('docs')}", file=out)
    print(f"  knowledge    : {config.path('knowledge')}", file=out)
    print(f"  registries   : {len(config.registries)}", file=out)
    for name, registry in sorted(config.registries.items()):
        print(f"    {name:<20} {registry.path}", file=out)
