---
type: Decision Record
id: ADR-2026-003
date: 2026-10-10
title: Local CI runner rehearses the pipeline before push
status: Accepted
decision: Provide tools/local_ci.py, a local runner that executes the same stages as ci.yml and fails when its own stages drift from the workflow.
covers: [MRB]
supersedes: []
---

# Context

GitHub Actions cannot be executed locally. Without a local rehearsal the first
execution of the pipeline is the push itself, so a syntax error, a drifted stage
or a missing dependency is discovered only after the work is public on a branch.

# Decision

`tools/local_ci.py` runs the same commands as `.github/workflows/ci.yml`,
stage-for-stage, and includes a **parity check** that parses the `jobs:` block of
the workflow and fails if a CI job has no local stage.

The `pre-push` hook invokes it, so a push is not the first test.

# Consequences

- Stage drift is detected mechanically. A runner whose stages silently diverge
  from the workflow is worse than no runner, because a green local run would
  then mean nothing.
- The runner is a **simulation**: it cannot reproduce runner images, the
  3.10–3.13 version matrix, caching or service containers. It says so in its own
  output, so nobody mistakes a local pass for a CI guarantee.
- A missing local tool is reported as `SKIP`, never as a silent pass.
- Cost: the runner must be kept in step with the workflow. The parity check is
  what keeps that honest rather than aspirational.
