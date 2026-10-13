---
type: Decision Record
id: ADR-2026-002
date: 2026-10-10
title: Branch guards are advisory on a free private repository
status: Accepted
decision: Implement branch-guard intent as compensating controls (CODEOWNERS, pre-push hook, CI gate, restricted token) and document explicitly that they are advisory because the hosting plan cannot enforce branch protection.
covers: [MRB]
supersedes: []
---

# Context

The delivery plan depends on "the agent cannot merge to `main`". That claim
needs enforcement. GitHub branch protection and rulesets both require GitHub Pro
for a private repository; both APIs returned HTTP 403 on the free plan.

# Decision

Keep the repository **free and private**, and implement guard *intent* as
compensating controls:

- `CODEOWNERS` requiring owner review for `.github/**`, `tools/**`, `tests/**`
  and the framework documents.
- A `pre-push` hook refusing direct pushes to `main`.
- A CI `governance` job that asserts the invariants on every pull request.
- Guidance to use a token without push rights to `main` for agent operations.

**These are advisory.** They make the wrong action visible and inconvenient;
they do not make it impossible.

# Consequences

- Honest limitation: a determined actor with a write token and `--no-verify`
  can still push to `main`. Documentation must say so rather than implying
  protection exists.
- Upgrading to GitHub Pro converts the advisory controls into enforced ones with
  no rework, because the controls are already written.
- The compensating controls are worth having regardless: CI catches what a local
  hook cannot, and `CODEOWNERS` records intent where a reader will find it.

# Alternatives rejected

- **Make the repository public** to obtain free protection. Rejected: it would
  expose the entire planning corpus, and the sandbox credential is in history.
- **Rely on process discipline alone.** Rejected: unenforceable and untestable.
