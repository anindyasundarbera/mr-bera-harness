"""Tests for tools/okf.py — the OKF v0.2 reader.

Covers the specification behaviours the module system depends on: frontmatter
parsing, trust tiers, staleness, path resolution, link walking, and the
conformance rules of SPEC section 11.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from conftest import write_concept
from harness.okf import (
    RESERVED_FILENAMES,
    Bundle,
    Concept,
    OkfError,
    parse_timestamp,
    split_frontmatter,
)

UTC = dt.timezone.utc


# --------------------------------------------------------------------------
# parse_timestamp — SPEC section 5: ISO 8601 with an explicit UTC offset
# --------------------------------------------------------------------------


class TestParseTimestamp:
    def test_offset_is_required(self) -> None:
        """A naive timestamp must be rejected; SPEC requires an explicit offset."""
        with pytest.raises(OkfError, match="lacks a UTC offset"):
            parse_timestamp("2026-10-10T13:00:00")

    def test_zulu_is_accepted(self) -> None:
        assert parse_timestamp("2026-10-10T13:00:00Z") == dt.datetime(
            2026, 10, 10, 13, 0, tzinfo=UTC
        )

    def test_explicit_offset_is_accepted(self) -> None:
        parsed = parse_timestamp("2026-10-10T13:00:00+05:30")
        assert parsed.utcoffset() == dt.timedelta(hours=5, minutes=30)

    def test_leading_trailing_whitespace_tolerated(self) -> None:
        assert parse_timestamp("  2026-10-10T00:00:00Z  ").year == 2026


# --------------------------------------------------------------------------
# split_frontmatter — SPEC section 4
# --------------------------------------------------------------------------


class TestSplitFrontmatter:
    def test_parses_a_normal_block(self) -> None:
        fm, body = split_frontmatter("---\ntype: Thing\n---\n\n# Body\n")
        assert fm == {"type": "Thing"}
        assert body.strip() == "# Body"

    def test_missing_block_raises(self) -> None:
        with pytest.raises(OkfError, match="missing or malformed"):
            split_frontmatter("# No frontmatter\n")

    def test_unterminated_block_raises(self) -> None:
        with pytest.raises(OkfError, match="missing or malformed"):
            split_frontmatter("---\ntype: Thing\n")

    def test_non_mapping_frontmatter_raises(self) -> None:
        with pytest.raises(OkfError, match="must be a YAML mapping"):
            split_frontmatter("---\n- a\n- b\n---\n")

    def test_unparseable_yaml_raises(self) -> None:
        with pytest.raises(OkfError, match="unparseable frontmatter"):
            split_frontmatter("---\ntype: [unclosed\n---\n")

    def test_empty_block_yields_empty_mapping(self) -> None:
        fm, _ = split_frontmatter("---\n---\n\nbody\n")
        assert fm == {}

    def test_only_leading_block_is_frontmatter(self) -> None:
        """A `---`-delimited example later in the body is NOT frontmatter.

        This is the hazard recorded in DOCUMENT_ROUTING.md section 5.1: a
        document that documents its own schema must not be parsed as carrying
        that schema.
        """
        text = (
            "---\n"
            "type: Template\n"
            "---\n\n"
            "# Example\n\n"
            "```yaml\n"
            "---\n"
            "type: SomethingElse\n"
            "canonical: true\n"
            "---\n"
            "```\n"
        )
        fm, body = split_frontmatter(text)
        assert fm == {"type": "Template"}
        assert "canonical: true" in body
        assert "canonical" not in fm

    def test_windows_line_endings(self) -> None:
        fm, _ = split_frontmatter("---\r\ntype: Thing\r\n---\r\n\r\nbody\r\n")
        assert fm == {"type": "Thing"}


# --------------------------------------------------------------------------
# Concept properties — SPEC sections 5.3, 5.4, 5.5
# --------------------------------------------------------------------------


def make_concept(tmp_path: Path, frontmatter: str, relpath: str = "concept.md") -> Concept:
    root = tmp_path / "b"
    root.mkdir(exist_ok=True)
    path = write_concept(root, relpath, frontmatter)
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return Concept(path=path, bundle_root=root, frontmatter=fm, body=body)


class TestTrustTier:
    """SPEC section 5.3, lowest to highest."""

    def test_absent_verified_is_unverified(self, tmp_path: Path) -> None:
        assert make_concept(tmp_path, "type: T").trust_tier == "unverified"

    def test_bare_mapping_is_one_element_list(self, tmp_path: Path) -> None:
        """SPEC section 11: consumers MUST treat a bare mapping as a one-element list."""
        c = make_concept(
            tmp_path, "type: T\nverified: { by: human:alice, at: 2026-10-10T00:00:00Z }"
        )
        assert c.trust_tier == "human-reviewed"

    def test_non_human_only_is_machine_confirmed(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T\nverified: { by: agent/v1, at: 2026-10-10T00:00:00Z }")
        assert c.trust_tier == "machine-confirmed"

    def test_any_human_verification_wins(self, tmp_path: Path) -> None:
        fm = (
            "type: T\n"
            "verified:\n"
            "  - { by: agent/v1, at: 2026-10-10T00:00:00Z }\n"
            "  - { by: human:alice, at: 2026-10-10T00:00:00Z }\n"
        )
        assert make_concept(tmp_path, fm).trust_tier == "human-reviewed"

    def test_human_prefix_is_required(self, tmp_path: Path) -> None:
        """`alice` without the `human:` prefix is not a human actor (SPEC section 7)."""
        c = make_concept(tmp_path, "type: T\nverified: { by: alice, at: 2026-10-10T00:00:00Z }")
        assert c.trust_tier == "machine-confirmed"


class TestStatus:
    """SPEC section 5.4."""

    def test_absent_status_defaults_to_stable(self, tmp_path: Path) -> None:
        assert make_concept(tmp_path, "type: T").status == "stable"

    def test_explicit_status_respected(self, tmp_path: Path) -> None:
        assert make_concept(tmp_path, "type: T\nstatus: draft").status == "draft"


class TestStaleness:
    """SPEC section 5.5: stale when now >= stale_after."""

    def test_absent_is_none(self, tmp_path: Path) -> None:
        assert make_concept(tmp_path, "type: T").is_stale() is None

    def test_past_is_stale(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T\nstale_after: 2020-01-01T00:00:00Z")
        assert c.is_stale() is True

    def test_future_is_fresh(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T\nstale_after: 2099-01-01T00:00:00Z")
        assert c.is_stale() is False

    def test_boundary_is_inclusive(self, tmp_path: Path) -> None:
        """now == stale_after is stale, not fresh."""
        moment = dt.datetime(2026, 6, 1, tzinfo=UTC)
        c = make_concept(tmp_path, "type: T\nstale_after: 2026-06-01T00:00:00Z")
        assert c.is_stale(moment) is True


# --------------------------------------------------------------------------
# Bundle loading — SPEC section 3 and 3.1
# --------------------------------------------------------------------------


class TestBundleLoading:
    def test_reserved_filenames_are_not_concepts(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "real.md", "type: T")
        (tmp_bundle / "index.md").write_text("# Index\n")
        (tmp_bundle / "log.md").write_text("# Log\n")
        assert set(Bundle(tmp_bundle).concepts()) == {"real"}
        assert {"index.md", "log.md"} == RESERVED_FILENAMES

    def test_nested_concepts_get_slash_separated_ids(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a/b/c.md", "type: T")
        assert "a/b/c" in Bundle(tmp_bundle).concepts()

    def test_concept_id_strips_md_suffix(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "deep/thing.md", "type: T")
        bundle = Bundle(tmp_bundle)
        assert "deep/thing" in bundle.concepts()
        assert "deep/thing.md" not in bundle.concepts()
        c = bundle.get("deep/thing")
        assert c is not None
        assert c.concept_id == "deep/thing"

    def test_get_accepts_md_suffix_and_slashes(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a/b.md", "type: T")
        bundle = Bundle(tmp_bundle)
        assert bundle.get("/a/b.md") is not None
        assert bundle.get("a/b") is not None
        assert bundle.get("a/missing") is None

    def test_concept_id_does_not_strip_every_dot(self, tmp_bundle: Path) -> None:
        """A filename with internal dots must keep them."""
        write_concept(tmp_bundle, "v1.2.notes.md", "type: T")
        assert "v1.2.notes" in Bundle(tmp_bundle).concepts()

    def test_malformed_concept_raises(self, tmp_bundle: Path) -> None:
        (tmp_bundle / "bad.md").write_text("# no frontmatter\n")
        with pytest.raises(OkfError, match="missing or malformed"):
            Bundle(tmp_bundle).concepts()

    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(OkfError, match="not a directory"):
            Bundle(tmp_path / "nope")

    def test_unknown_extra_keys_are_preserved(self, tmp_bundle: Path) -> None:
        """SPEC section 4.1: consumers MUST NOT reject unrecognized fields."""
        write_concept(tmp_bundle, "c.md", "type: T\nsomething_custom: 42")
        c = Bundle(tmp_bundle).get("c")
        assert c is not None
        assert c.frontmatter["something_custom"] == 42

    def test_by_type_and_by_tag(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: Metric\ntags: [x, y]")
        write_concept(tmp_bundle, "b.md", "type: Metric\ntags: [y]")
        write_concept(tmp_bundle, "c.md", "type: Other")
        b = Bundle(tmp_bundle)
        assert len(b.by_type("Metric")) == 2
        assert len(b.by_tag("y")) == 2
        assert len(b.by_tag("x")) == 1

    def test_unknown_type_is_tolerated(self, tmp_bundle: Path) -> None:
        """SPEC section 11: unknown `type` values must not cause rejection."""
        write_concept(tmp_bundle, "x.md", "type: SomethingNobodyRegistered")
        assert Bundle(tmp_bundle).check() == []


# --------------------------------------------------------------------------
# Path resolution and links — SPEC sections 6.1, 6.2
# --------------------------------------------------------------------------


class TestPathsAndLinks:
    def test_bundle_relative_path(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a/b.md", "type: T")
        b = Bundle(tmp_bundle)
        c = b.get("a/b")
        assert c is not None
        assert b.resolve_path(c, "/other/thing.md") == (tmp_bundle / "other" / "thing.md").resolve()

    def test_relative_path(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a/b.md", "type: T")
        b = Bundle(tmp_bundle)
        c = b.get("a/b")
        assert c is not None
        assert b.resolve_path(c, "./c.md") == (tmp_bundle / "a" / "c.md").resolve()

    def test_url_returns_none(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T")
        b = Bundle(tmp_bundle)
        c = b.get("a")
        assert c is not None
        assert b.resolve_path(c, "https://example.com/x.md") is None
        assert b.resolve_path(c, "s3://bucket/key") is None

    def test_links_extracted_and_images_ignored(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "a.md",
            "type: T",
            "See [b](/b.md) and ![img](/img.png) and [ext](https://x.test/y).",
        )
        c = Bundle(tmp_bundle).get("a")
        assert c is not None
        links = c.links()
        assert "/b.md" in links
        assert "/img.png" not in links, "image links are not concept links"
        assert "https://x.test/y" in links

    def test_broken_links_are_reported_not_fatal(self, tmp_bundle: Path) -> None:
        """SPEC section 11: broken cross-links must not cause rejection."""
        write_concept(tmp_bundle, "a.md", "type: T", "See [ghost](/ghost.md).")
        b = Bundle(tmp_bundle)
        assert b.broken_links() == [("a", "/ghost.md")]
        assert b.check() == []

    def test_link_edges_include_every_internal_body_link(self, tmp_bundle: Path) -> None:
        """Edges are reported for all internal links, matching SPEC section 6.1.

        SPEC is explicit that broken links are permitted and consumers MUST
        tolerate them, so graph building is deliberately permissive; existence
        checking is `broken_links()`'s job, not this one.
        """
        write_concept(tmp_bundle, "a.md", "type: T", "See [b](/b.md) and [g](/g.md).")
        write_concept(tmp_bundle, "b.md", "type: T")
        assert Bundle(tmp_bundle).link_edges() == [("a", "b"), ("a", "g")]

    def test_url_links_produce_no_edges(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T", "See [ext](https://x.test/y).")
        assert Bundle(tmp_bundle).link_edges() == []


# --------------------------------------------------------------------------
# Conformance — SPEC section 11
# --------------------------------------------------------------------------


class TestConformance:
    def test_conformant_bundle_has_no_problems(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T")
        assert Bundle(tmp_bundle).check() == []

    def test_missing_type_is_a_problem(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "title: No Type")
        problems = Bundle(tmp_bundle).check()
        assert any("missing required non-empty `type`" in p for p in problems)

    def test_empty_type_is_a_problem(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", 'type: ""')
        assert any("type" in p for p in Bundle(tmp_bundle).check())

    def test_actor_convention_violation_detected(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T\ngenerated: { by: alice }")
        problems = Bundle(tmp_bundle).check()
        assert any("actor convention" in p for p in problems)

    def test_valid_actor_forms_pass(self, tmp_bundle: Path) -> None:
        for actor in ("human:alice", "process:nightly", "agent/gemini-2.5"):
            write_concept(
                tmp_bundle,
                f"{actor.replace(':', '_').replace('/', '_')}.md",
                f"type: T\ngenerated: {{ by: {actor} }}",
            )
        assert Bundle(tmp_bundle).check() == []

    def test_non_mapping_generated_entry_detected(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T\ngenerated: [not, a, mapping]")
        assert any("not a mapping" in p for p in Bundle(tmp_bundle).check())

    def test_bad_stale_after_detected(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T\nstale_after: not-a-date")
        assert any("stale_after" in p for p in Bundle(tmp_bundle).check())

    def test_naive_stale_after_detected(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T\nstale_after: 2026-01-01T00:00:00")
        assert any("stale_after" in p for p in Bundle(tmp_bundle).check())

    def test_bad_status_detected(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "a.md", "type: T\nstatus: finished")
        assert any("status" in p for p in Bundle(tmp_bundle).check())

    def test_optional_families_may_be_absent(self, tmp_bundle: Path) -> None:
        """SPEC section 11: consumers MUST NOT reject for missing optional families."""
        write_concept(tmp_bundle, "a.md", "type: T")
        assert Bundle(tmp_bundle).check() == []


class TestAttestedComputationConformance:
    """SPEC section 10: required contract fields."""

    def test_runtime_required(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "c.md",
            "type: Attested Computation\nattester: { resource: /a.py }",
        )
        assert any("requires `runtime`" in p for p in Bundle(tmp_bundle).check())

    def test_attester_required(self, tmp_bundle: Path) -> None:
        write_concept(tmp_bundle, "c.md", "type: Attested Computation\nruntime: python")
        assert any("requires `attester`" in p for p in Bundle(tmp_bundle).check())

    def test_attester_resource_required(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "c.md",
            "type: Attested Computation\nruntime: python\nattester: { foo: bar }",
        )
        assert any("attester requires `resource`" in p for p in Bundle(tmp_bundle).check())

    def test_parameter_requires_name(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "c.md",
            "type: Attested Computation\n"
            "runtime: python\n"
            "attester: { resource: /a.py }\n"
            "parameters:\n"
            "  - { type: string }",
        )
        assert any("parameter entry requires `name`" in p for p in Bundle(tmp_bundle).check())

    def test_computation_must_be_a_path_not_a_url(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "c.md",
            "type: Attested Computation\n"
            "runtime: python\n"
            "attester: { resource: /a.py }\n"
            "computation: https://example.com/x.py",
        )
        assert any("must be a path" in p for p in Bundle(tmp_bundle).check())

    def test_complete_computation_is_conformant(self, tmp_bundle: Path) -> None:
        write_concept(
            tmp_bundle,
            "c.md",
            "type: Attested Computation\n"
            "runtime: python\n"
            "attester: { resource: /a.py }\n"
            "executor: { resource: /s.md, receipt: [stdout] }\n"
            "parameters:\n"
            "  - { name: x, type: string, required: true }",
        )
        assert Bundle(tmp_bundle).check() == []


# --------------------------------------------------------------------------
# Accessors used by the resolver
# --------------------------------------------------------------------------


class TestComputationAccessors:
    def test_executor_and_attester_default_to_empty(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T")
        assert c.executor() == {}
        assert c.attester() == {}
        assert c.runtime() == ""
        assert c.computation_file() is None
        assert c.parameters() == []

    def test_wrong_shape_is_coerced_safely(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T\nexecutor: not-a-mapping\nparameters: nope")
        assert c.executor() == {}
        assert c.parameters() == []

    def test_parameter_non_mapping_entries_filtered(self, tmp_path: Path) -> None:
        c = make_concept(tmp_path, "type: T\nparameters:\n  - valid\n  - { name: x }")
        assert c.parameters() == [{"name": "x"}]

    def test_title_falls_back_to_stem(self, tmp_path: Path) -> None:
        assert make_concept(tmp_path, "type: T", "nested/derived-name.md").title == "derived-name"
