---
type: Changelog Entry
id: CHG-2026-003
date: 2026-10-10
kind: fixed
title: Wire the missing subcommands, and stop writing into the wrong repository
summary: Four capabilities were unreachable from the CLI after the entry points were consolidated, and generated indexes were written into the harness repo instead of the invoking project.
covers: [MRB]
---

Two defects that only surfaced once a consumer actually depended on the harness.

**Four subcommands were missing.** Consolidating the duplicate `main()`
functions into one entry point removed the only way to run the guards, the
commit-convention check, the entry validator and the CI rehearsal. `AGENTS.md`
instructs agents to run the guards, so their absence was silent: the command
simply did not exist. All four are now wired in, and a test asserts that every
capability the documentation names is reachable.

**Generated files were written into the harness repository.** The output path for
`CHANGELOG.md` and `docs/DECISIONS_INDEX.md` derived from
`Path(__file__).resolve().parents[3]` — the package's own location. Running
`harness entries generate` inside a consumer therefore wrote into the *harness's*
working tree, silently modifying a different project. The path now derives from
the invoking directory.

Coverage rose from 74% to 89% once the subcommands were tested, which is itself
evidence that they had been untested.

274 tests, 89.4% coverage.
