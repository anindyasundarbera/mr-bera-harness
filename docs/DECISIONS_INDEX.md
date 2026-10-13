# Architecture Decision Index

> **Generated file — do not edit by hand.**
> Regenerate with `harness entries generate`.
> The authoritative entries live in `docs/decisions/`.

| ID | Date | Title | Status | Supersedes |
|---|---|---|---|---|
| `ADR-2026-021` | 2026-10-13 | Session continuity needs capture before it can offer resume, and the harness cannot read a transcript | Proposed | — |
| `ADR-2026-020` | 2026-10-13 | The handoff's mechanical facts are generated, and its narrative is not | Accepted | — |
| `ADR-2026-019` | 2026-10-13 | A code-to-decision link carries the decision's anchor hash, and is declared never inferred | Accepted | `ADR-2026-017` |
| `ADR-2026-018` | 2026-10-13 | Instruction resolution refuses rather than guesses, and calls no model | Accepted | — |
| `ADR-2026-017` | 2026-10-13 | Propose linking source code to the decisions that produced it | Superseded | — |
| `ADR-2026-016` | 2026-10-13 | The local CI rehearsal refuses to run a project it has no pipeline for | Proposed | — |
| `ADR-2026-015` | 2026-10-13 | Workflow changes route through SSH while agent credentials lack the workflow scope | Accepted | — |
| `ADR-2026-014` | 2026-10-13 | No PostgreSQL version is pinned, and the index stays rebuild-on-demand | Accepted | — |
| `ADR-2026-013` | 2026-10-13 | Session records live in git notes, and the ledger never executes | Accepted | — |
| `ADR-2026-012` | 2026-10-13 | The gates validate against JSON Schema via the standard library, and may not execute | Accepted | — |
| `ADR-2026-011` | 2026-10-13 | The usage dashboard is a static viewer, not a live actor | Accepted | — |
| `ADR-2026-010` | 2026-10-13 | Prompt budgets are exact word counts, and the budget is caller-supplied | Accepted | — |
| `ADR-2026-009` | 2026-10-13 | Scope fields are indexed element-wise so a scope query cannot over-select | Accepted | — |
| `ADR-2026-008` | 2026-10-13 | The build rehearsal does not gate on session guards | Accepted | — |
| `ADR-2026-007` | 2026-10-13 | The local CI runner resolves the invoking repository, not the package directory | Accepted | — |
| `ADR-2026-006` | 2026-10-13 | The document index is derived from git and must rebuild identically | Accepted | — |
| `ADR-2026-005` | 2026-10-10 | The harness owns the agent loop and the LLM only proposes | Accepted | — |
| `ADR-2026-004` | 2026-10-10 | Guards activate at the start of every agent session | Accepted | — |
| `ADR-2026-003` | 2026-10-10 | Local CI runner rehearses the pipeline before push | Accepted | — |
| `ADR-2026-002` | 2026-10-10 | Branch guards are advisory on a free private repository | Accepted | — |
| `ADR-2026-001` | 2026-10-10 | Changelog and ADR entries are append-only single files | Accepted | — |
