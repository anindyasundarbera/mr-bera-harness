---
type: Changelog Entry
id: CHG-2026-015
date: 2026-10-13
kind: added
title: Recorded the runtime dependency audit
summary: Audited and documented what the harness needs to run on any device or container, proving in a venv containing only PyYAML that no database, server or network is required and that every optional capability fails loudly with the fix in its message.
covers: [MRB]
---

The harness is meant to run wherever a coding agent runs, so the requirement was
audited rather than asserted. `docs/design/RUNTIME_DEPENDENCIES.md` records the
result.

## What was measured

An AST scan of every module finds exactly **three** third-party imports — `yaml`,
`jsonschema`, `psycopg` — and only `yaml` is core. Nothing under `src/` imports
`socket`, `http`, `urllib`, `ssl`, `asyncio` or `requests`: the harness never
reaches the network. The only external binary invoked anywhere is **`git`**.

A venv created with `pip install -e .` and **nothing but PyYAML** was run against a
real consumer project. Every command that does not need an extra worked fully:
`doctor`, `conform`, `context`, `guards`, `commits`, `entries`, `compile` and the
whole ledger. The two that do need one refused with the fix in the message —
`propose validate` named `pip install -e '.[propose]'`, and `index status` named
`MRB_HARNESS_DSN` and exited 3.

Notably, `harness.propose`, `harness.index` and `harness.ledger` all **import** with
no extras installed, because each defers its third-party import to the call that
needs it. A missing extra can therefore never break an unrelated command.

## The answer

A container needs `python>=3.11`, `git`, and `pip install mr-bera-harness`. The
database is optional and derived; there is no server, no daemon and no network
dependency. A repository with no database still has a complete document model and a
complete session ledger, because the facts live in git.

The audit also records its own limits: Python ≥ 3.11 is a declared floor (tested on
3.11–3.14; CI covers 3.11–3.13), and `git` is assumed present because a git
repository is the premise rather than a dependency that could sensibly degrade.

Refs: HARNESS-RUNTIME-001
