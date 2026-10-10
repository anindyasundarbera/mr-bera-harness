---
type: Decision Record
id: ADR-2026-001
date: 2026-10-10
title: Changelog and ADR entries are append-only single files
status: Accepted
decision: Record every change and decision as its own frontmatter-bearing file under knowledge/changelog and knowledge/decisions, and generate the human-facing CHANGELOG.md and decision index from them.
covers: [MRB]
supersedes: []
---

# Context

A single `CHANGELOG.md` that every branch appends to is a guaranteed merge
conflict, and resolving it by hand is exactly the kind of manual step that
loses an entry under time pressure.

# Decision

Authoritative entries are **one file per change** in `knowledge/changelog/` and
**one file per decision** in `knowledge/decisions/`. Each carries YAML
frontmatter. `CHANGELOG.md` and `docs/DECISIONS_INDEX.md` are **generated views**;
`python3 tools/entries.py generate` rewrites them and `--check` fails CI if they
drift.

# Consequences

- Two branches never edit the same file, so changelog conflicts are
  **structurally impossible** rather than merely unlikely.
- The generated files are derived, like the OKF bundle: they carry no authority.
- `tools/entries.py validate` runs in CI, so a malformed entry fails the build
  instead of silently vanishing from the changelog.
- Cost: contributors write frontmatter. The schema is small and validated.
