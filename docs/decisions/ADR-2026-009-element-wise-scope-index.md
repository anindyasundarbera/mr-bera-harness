---
type: Decision Record
id: ADR-2026-009
date: 2026-10-13
title: Scope fields are indexed element-wise so a scope query cannot over-select
status: Accepted
decision: Project list-valued routing fields (covers, blocks, depends_on, do_not_use_for, tags) into a document_field_items table with one row per element, so a scope query is an exact element match rather than a substring match that would silently select child scopes.
covers: [MRB]
supersedes: []
---

# Context

Build-order step 2 adds a query surface, and the most important question it must
answer is a scope question: *which documents cover `MRB-M06-S07`?*

The step 1 schema stored routing fields as JSON text in `document_fields`. A
scope query against that representation can only be a substring match:

```sql
WHERE value LIKE '%MRB-M06%'
```

That also matches `["MRB-M06-S07"]`, because `MRB-M06` is a prefix of `MRB-M06-S07`.
The query for the module would therefore return every document that covers any
child of that module — silent over-selection. Returning *more* than the truth is
the more dangerous failure: an agent given extra documents believes it has
grounding it does not have, and nothing in the output says otherwise.

This is the same failure the resolver exists to prevent. `harness.routing.resolve`
matches a scope with a set intersection on parsed list elements, never on text, so
it answers the question correctly today. A query surface that answered it
differently would make the two disagree, and the SQL form is the one an agent
reaches for because it is fast.

# Decision

List-valued routing fields are **projected element-wise** into
`document_field_items (path, key, item, ordinal)` — one row per element. Scalars
are projected the same way, so a lookup needs no branch.

A scope query is then a join, and `MRB-M06` matches only `MRB-M06`:

```sql
SELECT d.concept_id
FROM documents d JOIN document_field_items i ON i.path = d.path
WHERE i.key = 'covers' AND i.item = 'MRB-M06'
```

`INDEX_SCHEMA_VERSION` is raised to 2.

The step 1 rebuild invariant is untouched by this: `read_model` still
reconstructs the model from `document_fields`, so the digest and the
rebuild-identity test are unchanged. The new table is a query projection derived
from the same bytes, not a second source of truth.

# Consequences

- **The query cannot over-select.** Over-selection is now structurally impossible
  rather than a thing tests hope to catch. Two tests pin it: `MRB-M06` must not
  select a document that names only `MRB-M06-S07`, and it must select one that
  names `MRB-M06`.
- **The query surface agrees with the resolver by construction of the data, not
  by convention**, and a test compares them anyway — including against a real
  consumer repository.
- Cost: a wider schema. List fields occupy one row per element; the corpus is
  small and the index is rebuildable, so this is not a concern.
- Cost: two representations of a list field exist (`document_fields` for the
  model round-trip, `document_field_items` for queries). That is deliberate, and
  the reason is recorded here so a later reader does not "simplify" one away.
- The `gaps` lookup reads `registry_cells` by column *name*, never by position,
  for the same reason: a register whose column order changes must not silently
  change which value a column means.

# Alternatives rejected

- **Substring matching with word boundaries.** Fragile: `MRB-M06` appears inside
  `MRB-M06-S07` with a boundary at the hyphen, so any boundary rule either
  over-selects or under-selects on some identifier shape.
- **Parse the JSON in application code and filter in Python.** Correct, but it
  discards the reason for having SQL at all — it turns a join into a full scan
  plus Python, and removes the ability to aggregate.
- **Query Postgres JSON operators (`jsonb_array_elements`).** Workable, but the
  column type would have to change, and it makes every scope query depend on a
  type-specific incantation rather than a plain join.
- **Fix it in the resolver only.** The resolver already answers correctly. The
  gap was the query surface, so that is where the fix belongs.
