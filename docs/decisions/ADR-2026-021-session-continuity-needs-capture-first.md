---
type: Decision Record
id: ADR-2026-021
date: 2026-10-13
title: Session continuity needs capture before it can offer resume, and the harness cannot read a transcript
status: Proposed
decision: Record that a "resume from the last session" capability is desirable but cannot reconstruct an unrecorded session, because the ledger holds only caller-reported records, nothing writes them automatically, and a session transcript is not a repository artifact; capture must land first, and the agent supplies the narrative while the harness stores and verifies it.
covers: [MRB]
supersedes: []
---

# Context

The owner proposed two things (`2026-10-13`): that **the harness** should offer, when a
session opens, to **generate a handoff for the last session and continue from it**; and
that it should be able to **reconstruct what was done**.

The intent is the one this repository already serves — `PURPOSE.md` §6 asks that a
reader arrive at an unfamiliar repository and answer *what previous sessions did* without
asking anyone. So the goal is not in question. What is in question is whether the
capability as described can be built, and the four facts below were **measured**, not
assumed.

## 1. There is nothing to reconstruct from

`harness ledger list` in this repository returns **no records**, and
`git for-each-ref refs/notes` lists **no notes ref at all**. The ledger is a recorder,
and `ADR-2026-013` §3 is explicit: *"The ledger executes nothing. It records what the
caller reports."*

That caller is in practice the agent, and nothing compels it. `ledger append` is a
subcommand an agent must remember to run; no hook, no guard and no CI stage invokes it.
So a resume command built today would, in the normal case, answer *"nothing recorded"* —
honest, and useless.

**Consequence:** this is genuinely undecided in the owner's favour — the ledger was
built (step 5) and shipped, but the *practice* of recording was never established.
Capture is a missing practice, not a missing module.

## 2. The one existing history store is non-durable by design

`harness dashboard history` reads `.harness/`, which `.gitignore` line 36 excludes, and
`RUNTIME_DEPENDENCIES.md` / the store's own comment state the reason: *"run records and
the rendered dashboard are local, not source."* That is correct — git is authoritative
(`ADR-2026-006`) — but it means per-machine history does not survive a clone and cannot
be the substrate for "what the last session did".

**Consequence:** resume must read the **ledger in `git notes`**, which does survive a
copy (`ADR-2026-013`). There is no other candidate.

## 3. "What was done" is mostly not captured

The ledger records *prompt, proposal, verdict, effect* for a **work item**. It does not
record "PR #17 was opened", "a design decision was taken", "the handoff was refreshed".
A session's actual history lives in `git log`, the entries, and the handoff document —
which is exactly what `REMAINING_WORK.md` is for, and why it names its own revision rather
than deriving it.

**Consequence:** the honest capability is *"summarise what was **committed** since the
last handoff, and report what is **not** recorded"*, not *"reconstruct what was done"*.

## 4. The harness cannot know a session opened

The harness has no session concept. It has *session guards* (`ADR-2026-004`), but those
are named for the moment they are meant to run, not registered as a lifecycle hook:
nothing in `src/` runs them at session start. What makes an agent run them is a
**document** — this repository's `AGENTS.md`, and the brief a session is handed. This
repository has **no `AGENTS.md`** (the harness's own `AGENTS.md` is referenced six times
and does not exist, which is a separate recorded defect).

The harness is also deliberately non-interactive: a search of `src/` finds no `input()`,
no `getpass`, no prompt library — the only stdin read is `sys.stdin.read()` when an
argument is `-`. Every exit-code contract in this repository exists precisely so a caller
can branch **without** a human in the loop.

**Consequence:** "the harness asks the user at session start" is not a capability the
harness can hold. It is a property of the *host* that opens the session. The harness can
offer a **command**; something else must call it, and that something is not the harness.

## 5. The transcript is not a repository artifact

The decisive constraint. For the harness to *reconstruct* a session it would need the
conversation, and the conversation is not committed bytes. Two things follow:

- The harness reads committed git bytes (`ADR-2026-006`) and must keep doing so. Reading
  an agent's transcript would put the harness inside the agent's runtime, inverting
  `ADR-2026-005` — *the LLM proposes; the harness disposes* — by making the harness a
  consumer of the model's narrative.
- A model's account of what it did is a **claim**, not an observation. This is the same
  distinction `ADR-2026-019` draws for provenance (*declared, never inferred*) and
  `ADR-2026-017` refuses to violate. Generating a handoff by summarising a transcript
  would produce a plausible record of a session nobody can check — the exact failure
  `CHG-2026-016` and `CHG-2026-020` were raised for, one level up.

# Decision

**Status: `Proposed`.** Nothing described here is implemented. The owner has directed
that **capture is built first**; this record fixes the design of both halves and the
order, so the next session does not rediscover the four obstacles above.

## The split, which is the whole design

**The agent supplies the narrative; the harness stores and verifies it.** That is the
same division as `ADR-2026-017`/`019` for code provenance: *a person writes the
declaration and the tool only verifies it.* The harness never authors a session's story.

## Capture — the part with something to build

1. `harness ledger append` must actually be **run at the end of a session**, and its
   record must name the commit range and the outcome. An unrecorded session is the
   problem being solved, so the design must make recording the default rather than a
   remembered courtesy.
2. A **CI stage** can verify that a branch carries a ledger record before merge, which is
   the one enforcement point that exists without a host hook. This is the `Loud` class of
   `HARNESS_ARCHITECTURE.md` §7, not the `Impossible` class, and should be recorded as
   such.
3. The **handoff itself** is the durable narrative and is already being made derivable
   (`ADR-2026-020`): its mechanical facts are generated, its prose is a human edit.

## Resume — the part that must report what it cannot know

4. A `harness resume` command reads: the ledger notes since the last handoff, the commit
   range, and the handoff document. It emits **what is known** and **what is unknown**.
5. Its outcome is **three-valued**, like every other contract here:
   `reconstructed` / `partial` / `nothing-recorded`. It must never present a plausible
   summary of a session that was not recorded — an empty ledger yields
   `nothing-recorded`, not an inference from the commit subjects.
6. Whether the **host** prompts the user at session start is **the host's decision, not
   the harness's**. The harness exposes the command; a host hook may call it, and the
   hook is not part of this repository.

# Consequences

- **The order is fixed by observation, not preference.** Resume before capture reads an
  empty ledger in the normal case.
- **The harness stays outside the agent's runtime.** No transcript is read, so
  `ADR-2026-005` and `ADR-2026-006` are preserved and the validation surface stays
  testable code rather than a model's account.
- **A reader is told what is missing.** `nothing-recorded` is a real answer, and it
  points at the actual defect — that the session was never recorded — instead of
  hiding it behind a summary.
- Cost: capture needs discipline or enforcement, and neither is free. The CI stage is
  `Loud` and therefore bypassable with `--no-verify`, exactly like the branch guards
  (`ADR-2026-002`).
- Cost: the "harness asks at session start" experience the owner described needs a host
  hook that this repository does not control. Until it exists, the mechanism is a
  command a person or an agent runs — which is weaker than described, and is recorded as
  such rather than implied.
- **Stated limit:** this record does not decide *how* a session boundary is detected, nor
  the ledger fields a session-level record needs. Both are `DecisionRequired` and are
  the next thing to settle before capture is written.

# Alternatives rejected

- **Build resume first, from the ledger.** It would read an empty ledger; the feature
  would appear to work and answer nothing. Order matters.
- **Have the harness summarise the session transcript.** It would invent a record and
  put a model's narrative inside the deterministic layer — `ADR-2026-017`'s rejected
  failure, one level up.
- **Infer "what was done" from commit subjects and diffs.** An inference presented as a
  session record. The commit messages are evidence, not the narrative, and a summary
  built from them is a guess wearing provenance.
- **Reuse `.harness/` run records as the history.** Non-durable by design; a clone would
  lose it, and it records dashboard runs rather than sessions.
- **Make the harness interactive and prompt at startup.** Every contract in this
  repository is an exit code so a caller can branch without a human; a prompt would break
  scripting and put a lifecycle the harness cannot observe into the harness.
