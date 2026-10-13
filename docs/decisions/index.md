# Decision Records

One file per decision. These govern the harness itself; decisions a *consuming*
repository makes about its own delivery stay in that repository.

* [ADR-2026-001](ADR-2026-001-changelog-adr-entry-files.md) - changelog and ADR entries are single files.
* [ADR-2026-002](ADR-2026-002-advisory-branch-guards.md) - branch guards are advisory on a free private repository.
* [ADR-2026-003](ADR-2026-003-local-ci-runner.md) - a local CI runner rehearses the pipeline before push.
* [ADR-2026-004](ADR-2026-004-session-guard-activation.md) - guards activate at the start of every session.
* [ADR-2026-005](ADR-2026-005-harness-owns-loop.md) - the harness owns the loop; the LLM only proposes.
* [ADR-2026-006](ADR-2026-006-derived-index.md) - the document index is derived from git and must rebuild identically.
* [ADR-2026-007](ADR-2026-007-ci-runner-invoking-root.md) - the local CI runner resolves the invoking repository, not the package directory.
* [ADR-2026-008](ADR-2026-008-build-does-not-gate-on-session-guards.md) - the build rehearsal does not gate on session guards.
* [ADR-2026-009](ADR-2026-009-element-wise-scope-index.md) - scope fields are indexed element-wise, so a scope query cannot over-select.
* [ADR-2026-010](ADR-2026-010-budget-unit-and-no-default.md) - prompt budgets are exact word counts, and the budget is caller-supplied.
* [ADR-2026-011](ADR-2026-011-dashboard-is-a-viewer.md) - the usage dashboard is a static viewer, not a live actor.
* [ADR-2026-012](ADR-2026-012-proposals-validated-against-schema.md) - proposals validate against JSON Schema, and the gates may not execute.
* [ADR-2026-013](ADR-2026-013-session-ledger-in-git-notes.md) - session records live in git notes, and the ledger never executes.
* [ADR-2026-014](ADR-2026-014-no-version-pin-rebuild-on-demand.md) - no PostgreSQL version is pinned, and the index stays rebuild-on-demand.
* [ADR-2026-015](ADR-2026-015-workflow-changes-over-ssh.md) - workflow changes route over SSH while agent credentials lack the workflow scope.
* [ADR-2026-016](ADR-2026-016-ci-rehearsal-needs-a-pipeline.md) - **Proposed**: the local CI rehearsal runs the harness's own pipeline in a consumer.
* [ADR-2026-017](ADR-2026-017-code-to-decision-provenance.md) - **Proposed**: link source code to the decisions that produced it.
* [ADR-2026-018](ADR-2026-018-intent-resolution-refuses.md) - instruction resolution refuses rather than guesses, and calls no model.
