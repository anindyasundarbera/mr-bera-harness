---
type: Changelog Entry
id: CHG-2026-022
date: 2026-10-13
kind: added
title: Recorded why session resume needs capture first
summary: Recorded that "generate the last session's handoff and continue from it" is desirable but cannot reconstruct an unrecorded session, because the ledger holds only caller-reported records, nothing writes them, the local dashboard history is non-durable by design, and the harness cannot read a transcript; capture must land first, and the agent supplies the narrative while the harness stores and verifies it.
covers: [MRB]
---

The owner asked for two things on 2026-10-13: that **the harness** offer, at session
start, to **generate the last session's handoff and continue from it**; and that it be
able to **reconstruct what was done**. The intent is exactly what `PURPOSE.md` §6
already asks for, so the goal is not in dispute. Four obstacles are, and each was
measured this session rather than assumed.

## The four obstacles

| # | Finding | Measured how |
|---|---|---|
| 1 | There is nothing to reconstruct from | `harness ledger list` returns no records; `git for-each-ref refs/notes` lists nothing |
| 2 | The one history store is non-durable by design | `dashboard history` reads `.harness/`, excluded by `.gitignore:36` and documented as "local, not source" |
| 3 | "What was done" is mostly not captured | the ledger holds prompt/proposal/verdict/effect per work item, not "PR #17 was opened" |
| 4 | The harness cannot know a session opened | no session concept; no `input()`/prompt anywhere in `src/`; the only stdin read is `sys.stdin.read()` for `-` |

The decisive one is a fifth: **a session transcript is not a repository artifact.** For
the harness to *reconstruct* a session it would have to read the conversation, which
would put the harness inside the agent's runtime — inverting `ADR-2026-005` (*the LLM
proposes; the harness disposes*) — and would treat a model's account of what it did as an
observation rather than a claim. That is `ADR-2026-017`'s rejected failure one level up.

## What was decided, and what was refused

**`ADR-2026-021` (`Proposed`)** fixes the design and the order, on the owner's direction
that capture lands first:

- **The split:** the agent supplies the narrative; the harness stores and verifies it —
  the same division as code provenance, where *a person writes the declaration and the
  tool only verifies it*.
- **Capture** is the part with something to build: the ledger must actually be written at
  the end of a session, a CI stage can require a record on a branch (the `Loud` class of
  §7, bypassable with `--no-verify`, and recorded as such), and the handoff is the durable
  narrative now that its facts are generated (`ADR-2026-020`).
- **Resume** must be three-valued — `reconstructed` / `partial` / `nothing-recorded` — and
  must never present a plausible summary of a session that was recorded nowhere.
- **"The harness asks the user at session start" is refused as a harness capability:** it
  is a property of the host that opens the session. The harness exposes a command; a host
  hook may call it, and that hook is not in this repository.

Also refused: building resume before capture (it would read an empty ledger and appear to
work while answering nothing); summarising a transcript; and inferring "what was done"
from commit subjects, which is a guess wearing provenance.

**Stated limit:** the record does not decide how a session boundary is detected, nor which
ledger fields a session-level record needs. Both remain `DecisionRequired`.

**Tests:** no code changed. `harness doctor` clean, `harness entries validate` 0 problems.
