#!/usr/bin/env python3
"""OKF (Open Knowledge Format) v0.2 reader.

Project-agnostic: it parses whatever bundle root it is given.

Conforms to GoogleCloudPlatform/open-knowledge-format SPEC.md v0.2.

Read-only. Parses frontmatter, resolves path-valued fields, walks links, and
derives trust tier / staleness per SPEC sections 5.3-5.5 and 11.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("ERROR: PyYAML required. Install with: pip install pyyaml") from exc

RESERVED_FILENAMES = frozenset({"index.md", "log.md"})
# The block may be empty (`---\n---`), so `.*?` is required rather than `.+?`.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n?---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class OkfError(Exception):
    """Raised for a malformed concept document."""


def parse_timestamp(value: Any) -> _dt.datetime:
    """Parse an ISO 8601 datetime with explicit UTC offset (SPEC section 5)."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = _dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise OkfError(f"timestamp lacks a UTC offset: {value!r}")
    return parsed


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a concept document into (frontmatter, body).

    Only the leading block is frontmatter. Delimiter-like text later in the
    body (a fenced example, a template) is NOT frontmatter.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise OkfError("missing or malformed YAML frontmatter block")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise OkfError(f"unparseable frontmatter: {exc}") from exc
    except ValueError as exc:
        # PyYAML coerces an unquoted `YYYY-MM-DD` to a date and raises ValueError
        # (not YAMLError) for an invalid one, e.g. month 13. Without this catch a
        # single malformed entry would crash the whole validator.
        raise OkfError(f"invalid value in frontmatter: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise OkfError("frontmatter must be a YAML mapping")
    return data, text[match.end() :]


@dataclass
class Concept:
    """One OKF concept: a markdown document with YAML frontmatter."""

    path: Path
    bundle_root: Path
    frontmatter: dict[str, Any]
    body: str

    @property
    def concept_id(self) -> str:
        """Concept ID = bundle-relative path with .md suffix removed (SPEC section 2)."""
        return str(self.path.relative_to(self.bundle_root).with_suffix("")).replace("\\", "/")

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type", ""))

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.path.stem)

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description", ""))

    @property
    def is_attested_computation(self) -> bool:
        return self.type == "Attested Computation"

    @property
    def status(self) -> str:
        """SPEC section 5.4: absent => stable."""
        return str(self.frontmatter.get("status") or "stable")

    @property
    def trust_tier(self) -> str:
        """SPEC section 5.3, lowest to highest."""
        verified = self.frontmatter.get("verified")
        if not verified:
            return "unverified"
        entries = verified if isinstance(verified, list) else [verified]
        for entry in entries:
            by = str((entry or {}).get("by", "")) if isinstance(entry, dict) else ""
            if by.startswith("human:"):
                return "human-reviewed"
        return "machine-confirmed"

    def is_stale(self, now: _dt.datetime | None = None) -> bool | None:
        """SPEC section 5.5: stale when now >= stale_after. None when absent."""
        raw = self.frontmatter.get("stale_after")
        if not raw:
            return None
        now = now or _dt.datetime.now(_dt.timezone.utc)
        return now >= parse_timestamp(raw)

    def links(self) -> list[str]:
        """Markdown links in the body (SPEC section 6.1)."""
        return [m for m in _LINK_RE.findall(self.body) if not m.startswith("#")]

    def parameters(self) -> list[dict[str, Any]]:
        raw = self.frontmatter.get("parameters") or []
        return [p for p in raw if isinstance(p, dict)]

    def runtime(self) -> str:
        return str(self.frontmatter.get("runtime", ""))

    def executor(self) -> dict[str, Any]:
        raw = self.frontmatter.get("executor")
        return raw if isinstance(raw, dict) else {}

    def attester(self) -> dict[str, Any]:
        raw = self.frontmatter.get("attester")
        return raw if isinstance(raw, dict) else {}

    def computation_file(self) -> str | None:
        raw = self.frontmatter.get("computation")
        return str(raw) if raw else None


# Status vocabularies that differ from the OKF document lifecycle (SPEC section
# 5.4). A `Decision Record` carries an editorial status, not a document
# lifecycle status. Unregistered types fall back to the OKF enum.
OKF_LIFECYCLE = frozenset({"draft", "stable", "deprecated"})
STATUS_VOCABULARY_BY_TYPE: dict[str, frozenset[str]] = {
    "Decision Record": frozenset(
        {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded", "ArchitectureSelected"}
    ),
}


def allowed_statuses(concept_type: str) -> frozenset[str]:
    """The set of legal `status` values for a concept type."""
    return STATUS_VOCABULARY_BY_TYPE.get(concept_type, OKF_LIFECYCLE)


class Bundle:
    """A knowledge bundle: a directory tree of concept documents (SPEC section 3)."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise OkfError(f"bundle root is not a directory: {self.root}")
        self._concepts: dict[str, Concept] | None = None

    def concepts(self, *, refresh: bool = False) -> dict[str, Concept]:
        if self._concepts is not None and not refresh:
            return self._concepts
        found: dict[str, Concept] = {}
        for md in sorted(self.root.rglob("*.md")):
            if md.name in RESERVED_FILENAMES:
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise OkfError(f"{md}: not valid UTF-8 ({exc})") from exc
            fm, body = split_frontmatter(text)
            cid = str(md.relative_to(self.root).with_suffix("")).replace("\\", "/")
            found[cid] = Concept(md, self.root, fm, body)
        self._concepts = found
        return found

    def get(self, concept_id: str) -> Concept | None:
        key = concept_id.strip("/").removesuffix(".md")
        return self.concepts().get(key)

    def by_type(self, type_name: str) -> list[Concept]:
        return [c for c in self.concepts().values() if c.type == type_name]

    def by_tag(self, tag: str) -> list[Concept]:
        return [c for c in self.concepts().values() if tag in (c.frontmatter.get("tags") or [])]

    def resolve_path(self, concept: Concept, value: str) -> Path | None:
        """Resolve a path-valued field (SPEC section 6.2). URL => None."""
        if _URL_RE.match(value):
            return None
        if value.startswith("/"):
            return (self.root / value.lstrip("/")).resolve()
        return (concept.path.parent / value).resolve()

    def _to_concept_id(self, path: Path) -> str | None:
        try:
            return str(path.relative_to(self.root).with_suffix("")).replace("\\", "/")
        except ValueError:
            return None

    def link_edges(self) -> list[tuple[str, str]]:
        """(source_id, target_id) for internal body links."""
        edges: list[tuple[str, str]] = []
        for concept in self.concepts().values():
            for raw in concept.links():
                target = self.resolve_path(concept, raw)
                if target is None:
                    continue
                tid = self._to_concept_id(target)
                if tid:
                    edges.append((concept.concept_id, tid))
        return edges

    def broken_links(self) -> list[tuple[str, str]]:
        """Internal links whose target is not a concept. Not an error (SPEC section 11)."""
        ids = set(self.concepts())
        broken: list[tuple[str, str]] = []
        for concept in self.concepts().values():
            for raw in concept.links():
                target = self.resolve_path(concept, raw)
                if target is None:
                    continue
                tid = self._to_concept_id(target)
                if tid and tid not in ids:
                    broken.append((concept.concept_id, raw))
        return broken

    def check(self) -> list[str]:
        """Conformance problems per SPEC section 11. Empty => conformant."""
        problems: list[str] = []
        for cid, c in self.concepts().items():
            if not c.type.strip():
                problems.append(f"{cid}: missing required non-empty `type`")

            for fname in ("generated", "verified"):
                entry = c.frontmatter.get(fname)
                if entry is None:
                    continue
                entries = entry if isinstance(entry, list) else [entry]
                for item in entries:
                    if not isinstance(item, dict):
                        problems.append(f"{cid}: {fname} entry is not a mapping")
                        continue
                    by = str(item.get("by", ""))
                    if not by:
                        problems.append(f"{cid}: {fname} entry lacks `by`")
                    elif not (by.startswith("human:") or by.startswith("process:") or "/" in by):
                        problems.append(
                            f"{cid}: {fname}.by `{by}` violates the actor convention "
                            "(human:<id> | process:<id> | <producer>/<version>)"
                        )

            raw_stale = c.frontmatter.get("stale_after")
            if raw_stale:
                try:
                    parse_timestamp(raw_stale)
                except (OkfError, ValueError):
                    problems.append(f"{cid}: stale_after is not an ISO 8601 timestamp")

            if c.status not in allowed_statuses(c.type):
                permitted = "|".join(sorted(allowed_statuses(c.type)))
                problems.append(f"{cid}: status `{c.status}` not in {permitted}")

            if c.is_attested_computation:
                if not c.runtime():
                    problems.append(f"{cid}: Attested Computation requires `runtime`")
                att = c.attester()
                if not att:
                    problems.append(f"{cid}: Attested Computation requires `attester`")
                elif not att.get("resource"):
                    problems.append(f"{cid}: attester requires `resource`")
                for param in c.parameters():
                    if not param.get("name"):
                        problems.append(f"{cid}: parameter entry requires `name`")
                for path_field in ("computation",):
                    raw = c.frontmatter.get(path_field)
                    if raw and self.resolve_path(c, str(raw)) is None:
                        problems.append(f"{cid}: {path_field} must be a path, not a URL")
        return problems
