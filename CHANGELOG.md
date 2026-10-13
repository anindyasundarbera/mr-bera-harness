# Changelog

> **Generated file — do not edit by hand.**
> Regenerate with `harness entries generate`.
> The authoritative entries live in `knowledge/changelog/`.

## 2026-10-13

### Changed: ADR-2026-017 is superseded, and the duplicate decision index no longer restates status

*Settled ADR-2026-017's status by supersession -- ADR-2026-019 records supersedes [ADR-2026-017] and 017 becomes Superseded, keeping the proposal it made while removing the disagreement about a capability that now exists; and made docs/decisions/index.md a pure pointer, because it hand-synced statuses for two records only and nothing tested it.*

- **ID:** `CHG-2026-023`  
- **Covers:** `MRB`

Two changes with one cause: a fact stated in more than one place, and only one of those
places generated.

## The status was genuinely `Proposed`, not an out-of-sync artifact

The owner asked whether `ADR-2026-017`'s `Proposed` status in the *Architecture Decision
Index* was a forgotten update. It was not: the index is generated, and it faithfully
reported the **source record**, which carried `status: Proposed` and a `decision:` field
saying *"the mechanism is undecided and nothing is implemented."*

So this was never an artifact-sync defect. It was an unmade decision, recorded as
decision 7 in `REMAINING_WORK.md`, which exists precisely to flag that `ADR-2026-017`
now contradicted `ADR-2026-019` — a record that *implemented* the capability 017 only
proposed.

**Resolved by supersession**, on the owner's direction:

| Record | Change |
|---|---|
| `ADR-2026-019` | `supersedes: [ADR-2026-017]` |
| `ADR-2026-017` | `status: Superseded`; its normative `decision:` and body opening now state the supersession and point at 019 |

Supersession was chosen over marking 017 `Accepted` because 017's `decision:` field says
nothing was implemented, and that was **true of 017**. Rewriting it to `Accepted` would
have made its body assert an implementation it never had; leaving its text as the
proposal and superseding it keeps every record honest.

**The digest boundary makes this safe.** `supersedes` is deliberately **not** in
`NORMATIVE_FIELDS` (`provenance/links.py`), so recording the supersession does not stale
the two files that declare a decision. Verified: `harness provenance check` still exits
`0`. Only the `status` and `decision` edits on 017 touch normative content, and no file
declares 017.

## The duplicate index, which is the real sync hazard

`docs/decisions/index.md` was **hand-maintained** and restated each record's title and —
for `ADR-2026-016` and `-017` only — its status. It was updated by hand in PR #15 because
someone remembered; `harness entries generate` does not write it, no test reads it, and
`harness doctor` does not check it. It also sat one directory away from the **generated**
`docs/DECISIONS_INDEX.md`, whose name differs by case and path — easy to edit the wrong
one.

That is a second copy of a fact with nothing checking it: the failure `CHG-2026-016`
(hardcoded header) and `CHG-2026-020` (stale README) were both raised for.

It is now a **pure pointer**. It names the generated index, says which file is
authoritative, and repeats no list and no status — so there is nothing left in it to
drift. This is the owner's own principle applied: *point at the artifact rather than
restate it verbatim*, so an agent consumes one authority instead of several copies.

`REMAINING_WORK.md` decision 7 is closed and its change history records v2.3.

## A live reproduction of decision 8, while resolving the merge

Resolving this PR's conflict against `main` produced a failure worth recording, because
the cause was proven rather than inferred. With the merge resolved but **not yet
committed**, `tests/test_dashboard.py::test_guards_on_a_feature_branch_pass` failed —
the exact environment dependency §5.2 describes. The evidence:

```
merge-base HEAD origin/main = bcccc14…   # the pre-merge tip, one commit behind
→ guards reported `fail`; the test failed
(create the merge commit)
merge-base HEAD origin/main = 4740647…   # now the tip
→ the same test passed, unchanged
```

**Nothing in the branch or the test changed between the two runs — only the checkout's
position did.** That is decision 8's second consequence demonstrated on demand instead
of described, and §5.2 now records the reproduction. The defect itself is still unfixed:
it is a semantics question about the `branch` argument's contract, and it remains the
owner's to decide.

**Tests:** 624 without a database; coverage 82.2%. `harness doctor` clean (44 entries,
0 problems), `harness provenance check` exit 0, `refresh_handoff.py --check` exit 0.

### Added: Recorded why session resume needs capture first

*Recorded that "generate the last session's handoff and continue from it" is desirable but cannot reconstruct an unrecorded session, because the ledger holds only caller-reported records, nothing writes them, the local dashboard history is non-durable by design, and the harness cannot read a transcript; capture must land first, and the agent supplies the narrative while the harness stores and verifies it.*

- **ID:** `CHG-2026-022`  
- **Covers:** `MRB`

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

### Added: The handoff's facts are generated, so they stop going stale

*Split docs/design/REMAINING_WORK.md into hand-written narrative and a marker-delimited region refreshed by tools/refresh_handoff.py from the harness's own derivations, with a --check mode that exits 1 on staleness; the region holds only facts that are functions of the committed content.*

- **ID:** `CHG-2026-021`  
- **Covers:** `MRB`

The handoff is the first document a new session is told to trust, and it has already
been wrong once — the v2.0 refresh found it describing steps 1–3 as the state and steps
4–6 as "not started" when all six were merged. That was fixed by rewriting it. The
*facts* that were wrong are the kind a machine knows exactly, and they had been
refreshed by hand, so they were due to decay again the moment the next change landed.

## What changed

`docs/design/REMAINING_WORK.md` now carries a generated region delimited by
`<!-- harness:handoff-facts:start/end -->`. `tools/refresh_handoff.py` fills it with
values **derived** from the repository through the harness's own library:

| Fact | Derived from |
|---|---|
| OKF concepts | the `Bundle` reader |
| entries, problems | the entries `validate_all` |
| test modules | the configured tests directory |
| provenance declarations | the provenance `check` |
| commit vocabulary | the resolved `Config` |

Nothing is re-implemented. A second implementation would be a second definition of "the
entry count", and the two would drift — the defect, reintroduced in the fix.

## The design decision that came from building it

The first implementation also rendered **the revision** and **the test pass/skip
counts**. Both were removed, and the reason is worth recording because it was found by
observation rather than by reasoning ahead:

- **A committed file cannot contain its own commit's hash.** A region stating
  `Revision: <HEAD>` is stale the instant it is committed, so `--check` could never
  return `0` and the scheduled job would rewrite the same lines forever.
- **The test counts describe the environment.** The same commit reports one pair without
  a database and a different pair with one, so the check would differ between a laptop
  and CI — the class of defect already paid for twice here (a coverage floor measured
  differently with and without `MRB_TEST_DSN`).

The rule, stated once: **the region holds only facts that are functions of the committed
content.** A fact about the checkout or the machine is not a fact about the repository.
The rule is pinned by a test that asserts the `Facts` dataclass carries none of those
fields, so re-adding one fails with the reason attached.

## What deliberately did not change

**The narrative.** What was built, what is blocked, what is next is a judgement; a
script that produced it would be inventing a handoff. Only the marked region is
generated, and the splice is tested to leave every byte outside it untouched.

## The interface

```
refresh_handoff.py            # refresh the region (exit 0)
refresh_handoff.py --check    # exit 1 if stale, 2 if the handoff has no markers
```

The `1` is what a scheduled job acts on without mutating anything. A handoff with no
markers exits `2` rather than doing nothing quietly — a silent no-op would report
success while refreshing nothing.

## Proven, not asserted

- Tampering with a derived value (`OKF concepts 21` → `20`) made `--check` exit **1**;
  the refresher restored it and `--check` returned **0**.
- **The region settles on a committed tree.** `--check` returns `0` after a real commit,
  which the first design could not have achieved by construction.

**Stated limit:** the script proves the region matches the repository's derivations. It
cannot prove the narrative is true — the v1.0 staleness was prose, and no marker catches
prose.

**Tests:** 624 without a database (18 new); coverage 82.2%. Lint, format,
`mypy --strict`, `harness doctor`, `harness provenance check` and `harness ci` all clean.

### Fixed: The README no longer claims a gap the repository has closed

*PR*

- **ID:** `CHG-2026-020`  
- **Covers:** `MRB`

The same class of defect `CHG-2026-016` fixed in the generated header — a document
asserting something the repository no longer makes true — reappeared one file over,
because the change that closed the gap updated `docs/PURPOSE.md` and every design
note it owns, but not the README that links to it.

## Three contradictions, all in one file

1. **A closed gap still described as open, twice.** `README.md:19` said
   *"including the one gap it does not yet close: there is no checked link from a
   line of code to the decision that produced it"* and `README.md:154` repeated it.
   `PURPOSE.md` §4 now says the opposite — *"Recently closed — the gap this document
   previously named as the principal one"* — and `harness provenance check` exits 0.
   The README therefore **contradicted the document it links to**, which is the
   drift this repository exists to catch.
2. **A broken internal path.** `README.md:134` pointed at
   `docs/HARNESS_ARCHITECTURE.md`; the file is `docs/design/HARNESS_ARCHITECTURE.md`.
   Line 143 of the same file already had it right.
3. **An undocumented shipped command.** The Status section said *"All six build-order
   components are implemented"* while `harness provenance` — built beyond the build
   order — appeared nowhere in the README, unlike every other command group.

## The fix, and the check that stops the recurrence

The two false claims are replaced with wording that does not overclaim, the path
becomes `docs/design/`, and the provenance commands join the command list.

The larger point is that nothing caught this: no test read the README, and
`harness doctor` does not. `tests/test_readme.py` now checks that every relative link
in the README resolves to a tracked file, so a moved or misspelled path fails the
suite rather than a reader.

Stated plainly: the test checks that a link **resolves**, not that its *target is
still true*. Claim 1 above — a document asserting a stale fact — is not machine-checkable
from a link, and this test does not pretend otherwise. What it removes is the class
where the README points at a file that is not there.

**Tests:** 606 without a database (6 new); coverage unchanged at 82.2%. Lint, format,
`mypy --strict`, `harness doctor` and `harness ci` all clean.

### Added: Code provenance — every file can declare the decision that produced it

*Closed the gap docs/PURPOSE.md named, by letting a source file declare the decisions binding it with the decision's anchor hash, so a revised decision flags every implementing file as stale; the links are checked in CI and written to the derived index for joins.*

- **ID:** `CHG-2026-019`  
- **Covers:** `MRB`

Closes the principal gap `docs/PURPOSE.md` §4 named in its own honest list: *"code has
no provenance link to the decisions that produced it."* Implements `ADR-2026-017`;
the mechanism is `ADR-2026-019`.

```bash
harness provenance marker ADR-2026-009     # the line to paste
harness provenance check                   # verify every declaration
harness provenance map                     # what declares each decision
harness provenance index                   # the same links, in the derived index
```

## The hash is what makes it a check rather than a comment

A declaration carries the decision's **anchor digest**:

```python
# harness:decision ADR-2026-009 sha256:a6d5f77e7cfb
```

Edit the decision and the hash stops matching, so every file that implements it is
reported stale — with both hashes and an actionable message:

```
STALE (1) — the decision changed after this was written
  src/harness/index/schema.py:19  `ADR-2026-009` has changed since this file declared it
  (declared sha256:a6d5f77e7cfb, now sha256:6958e364bfac)
```

**Demonstrated, not asserted:** editing `ADR-2026-009` in the real repository flipped
`index/schema.py` from verified to stale in one command. Restoring the decision
returned it to green.

## The digest boundary is deliberate

Covered: `id`, `title`, `status`, `decision`, `covers`, and the **first prose
paragraph**. Excluded: `date`, `supersedes`, the change-history table, later narrative.
A digest that moved for a date would cry wolf until nobody read it — and then the real
finding would be ignored too. Tests assert **both** directions of that boundary.

## Nothing is inferred

A person writes the declaration; the tool only verifies it. No model, no network, no
shell — asserted from the module's own imports by a test. An inferred link would be a
guess presented as provenance, which is precisely what this project refuses to do.

`broken` (the decision does not exist) and `stale` (it exists and changed) are reported
separately, because they call for different actions. `unlinked` is reported only with
`--require-all`: requiring a declaration on every file produces ceremony, not
provenance.

## In the codebase and in the index

`harness provenance index` writes `decisions` and `code_links`, so *"which code was
written against a decision that has since changed?"* is a **join** across the whole
repository rather than a file-by-file check. Derived and reset on each write, like
every other store here — a declaration removed from a file disappears from the index.

## Two bugs found while building

1. **A false positive, immediately.** The package's own docstrings *document* the
   marker, so the scanner parsed its own documentation as declarations. Fixed by
   requiring a comment introducer at line start. A checker that reports false positives
   gets ignored, and then the real finding is ignored too.
2. **A declaration placed inside a SQL string, by an automated placer.** It inserted
   after the first line ending in a triple quote — which in `index/schema.py` was
   **inside the DDL**. The SQL stopped being valid while the file still parsed as
   Python, so the damage was invisible until a test connected to a database. A second
   insertion landed inside a dataclass body. Both repaired, and a test now walks the
   AST of every source file to prove no declaration sits inside a string literal or a
   class body.

## What it does not verify

A file can declare a decision **unrelated** to it. The check verifies the decision
exists and has not moved — **not** that the code implements it. An undeclared change
remains invisible. Stated in the design note rather than left to inference.

**Tests:** 600 without a database; **676 with a live PostgreSQL**, coverage 91.4%
(`store.py` 100%, `links.py` 95%). Lint, format, `mypy --strict`, `harness doctor`,
`harness guards` and `harness ci` all clean.

### Added: Instruction to work item — resolved when unique, asked when not

*Implemented build-order step 6, the one step rated not deterministic, as a resolver that extracts identifiers the instruction names, scores the decomposition lexically, and refuses with a clarification request whenever the answer is not unique, calling no model.*

- **ID:** `CHG-2026-018`  
- **Covers:** `MRB`

Implements build-order step 6 of `HARNESS_ARCHITECTURE.md` §9 — *human intent to
compiled prompt* — the last component and the only one the architecture rates **not
deterministic**.

```bash
harness intent resolve "work on MRB-M06-S07"
harness intent resolve "the model set and hardware envelope"
harness intent resolve "whatever I meant" --work-id MRB-M06-S01 --budget 4000
```

## What §8 permits, implemented exactly

§8 says a fuzzy classifier is not achievable and states what to build instead:
*deterministic prompt **assembly**; intent resolution is explicit and fallible, with a
human-clarification fallback.* So this is not a classifier:

1. **Exact extraction** — identifiers the instruction already contains, per the
   configured grammar. Not inferred: the grammar decides.
2. **Lexical scoring** — against each declared identifier *and the concepts that cover
   it*, so a phrase can reach an identifier through a concept title.
3. **Refusal** — two candidates, a tie, a close runner-up, or nothing above the cut is
   a **clarification request**, never a pick.

**No model, no network, no shell.** §4's rule is explicit that a model in the
extraction path makes the system *"probabilistic wearing a deterministic label"*.

## The refusal is the feature

§9 says the design must not depend on this step, which makes a wrong guess **worse**
than no answer: it would compile a prompt bound to the wrong work item and present it
as authoritative — and nothing downstream would catch it, because everything after is
deterministic.

| Situation | Status | Exit |
|---|---|---|
| exactly one identifier named | `resolved` | 0 |
| one candidate above the cut, no close runner-up | `resolved` | 0 |
| two or more identifiers named | `ambiguous` | 3 |
| candidates tied, or a leader within 80% of a runner-up | `ambiguous` | 3 |
| nothing above the cut | `unresolved` | 4 |

Observed on a real corpus:

```
$ harness intent resolve "the model set and hardware envelope"
status : ambiguous
reason : `MRB-M06-S03` leads on 0.50 but `MRB-M06-S07` is close on 0.40; ask which
```

A leader at 0.50 against 0.40 is real signal and still a question. And an explicit
`--work-id` bypasses resolution entirely — the architecture's point that a human
naming the ID loses nothing — with the reason stating *"nothing was inferred"* rather
than pretending it resolved something.

## Two bugs found while building, both about the identifier grammar

1. **The validating grammar cannot scan.** `identity.id_pattern()` is anchored
   (`\A…\Z`), so `re.search` with it never matches inside prose — an instruction
   naming `MRB-M06-S07` resolved to *nothing*, the most common case failing.
2. **The scan pattern lost the nesting.** Concatenating the level groups made every
   level mandatory, so it matched almost no real identifier. The validating grammar
   *nests* its optional groups; the scan pattern now nests identically.

Both were caught by tests describing *behaviour* — a one-level identifier must work —
rather than implementation.

## Project-agnostic, verified in a fresh consumer

A `EPIC` prefix with `P/S` levels, a `kb/` bundle, `specs/` docs:

| Instruction | Result |
|---|---|
| `work on EPIC-P01-S01` | `resolved` |
| `EPIC-P01 and EPIC-P01-S02` | `ambiguous` (exit 3) |
| **`the ledger writer`** | `resolved` → `EPIC-P01-S01`, reached via the *concept* title |
| `something entirely unrelated here` | `unresolved` (exit 4) |

The third row is why scoring uses concepts: a phrase in no identifier reached the
right one.

**Tests:** 557 without a database; **629 with a live PostgreSQL**, coverage 91.5%
(`intent/resolve.py` 98%). Lint, format, `mypy --strict`, `harness doctor`,
`harness guards` and `harness ci` all clean.

### Added: Stated the repository's purpose, and the gap it does not yet close

*Added docs/PURPOSE.md framing the repository as a live system rather than a folder of documents, stating separately what is implemented and what is aimed at; proposed code-to-decision provenance as the missing edge, and fixed a duplicated sentence and a stale status section in the README.*

- **ID:** `CHG-2026-017`  
- **Covers:** `MRB`

The framing of the repository was implicit. It is now stated, and — more
importantly — split into what is true and what is aimed at.

## `docs/PURPOSE.md`

The problem: a running system tells you what it is doing, a codebase does not. The
knowledge that produced the code lives in heads, chat threads, or documents nobody
re-reads, and prose has no exit code — so a stale description is indistinguishable
from a current one.

The intention: treat the repository as a **live system**. The distinguishing
property is not that answers exist, but that they are **computed and refutable** — a
document that disagrees with the repository fails `harness doctor`, a decision
without its reasoning fails the entry schema, an undecided value stops work with an
exit code.

The most useful part is §4, which separates two lists. Implemented and tested:
decision records with reasoning, `harness context`, the extract/query layer, the
prompt compiler, proposal gating, the session ledger, the dashboard, and an audited
runtime. Not yet true, and named as the principal gap:

> **Code has no provenance link to the decisions that produced it.** A file cannot
> say *"this exists because of `ADR-2026-009`"*. The reasoning is recorded and the
> code is recorded, but the edge between them is not.

## `ADR-2026-017` — `Proposed`

Records that gap as something aimed at rather than implied. It proposes that a
source file may **declare** the decisions binding it, checked by CI so the link
cannot rot — and it lists four things deliberately left undecided (the mechanism,
the direction, whether it is mandatory, how it is surfaced). It also states a risk
worth weighing: a declaration checked for *existence* is still not checked for
*truth*.

`Proposed`, not `Accepted`, for the reason established in `CHG-2026-016`: nothing is
implemented, and an `Accepted` record describing unimplemented behaviour is a false
record.

## Two README defects, fixed

- The Status section contained a **duplicated sentence** — the Step 3 description
  appeared twice, a real instance of the staleness this framing is about.
- The Status section was several steps behind, describing steps 1–3 while five were
  merged. It now states steps 1–5, names step 6 as not built, and links the purpose.

## A cross-branch dependency, caught and removed

This branch was started from `main` while `fix/close-blockers` was still open, and
initially referenced `ADR-2026-015`, `ADR-2026-016` and `CHG-2026-016`, which live on
that unmerged branch. That is branch stacking by reference — the hazard the guards
exist for — and it would have broken `harness doctor` on this branch, since a cited
record would not exist.

Every reference was checked mechanically: each cited record either exists on `main`
or is created by this branch. This branch now stands alone.

Refs: ADR-2026-017

### Fixed: Closed the recorded blockers — two defects fixed, four status-quo records added

*Fixed the generated header hardcoding a source path and the dashboard reporting a vacuous routing pass, and recorded four previously-open items as ADRs stating what the code does today, what was chosen implicitly, and which parts remain the owner's decision.*

- **ID:** `CHG-2026-016`  
- **Covers:** `MRB`

Closing the blockers meant separating two kinds of item that had been listed
together.

## Two mechanical defects, fixed

**1. A generated file stated a location it was not told.**
`docs/DECISIONS_INDEX.md` said the authoritative entries live in
`knowledge/decisions/`, while `harness.toml` configures `docs/decisions` — and the
text was **hardcoded** in `entries/generator.py`. This is the same class as the four
location defects already fixed: a library answering about its own context instead of
its caller's. The renderers now take the configured path, so the header states where
*this* project keeps its entries. Two tests pin it, including the exact case that
exposed it.

**2. The dashboard reported a vacuous pass.**
`routing invariants  pass  0 violation(s) over 0 concept(s)` — a pass over
**nothing checked**. The harness's own bundle triggers it, because `validate_routing`
deliberately skips changelog and decision entries, which is all that bundle holds. It
is now `unknown` with the reason stated, applying the dashboard's own three-valued
rule to itself. A test covers it.

## Four items recorded at their true status

An ADR each, stating what the code does today and which parts remain the owner's —
because inventing a PostgreSQL version or a credential policy is exactly what must
not happen:

| Record | What it settles | What stays open |
|---|---|---|
| `ADR-2026-014` | no version pinned anywhere; the index is rebuild-on-demand; the `postgres:16` image in CI is a **test fixture, not a support claim** | the supported version range, locality, whether a long-running service is ever wanted |
| `ADR-2026-015` | workflow changes route over SSH with the owner's key; no credential shared or widened; the `gh`-says-SSH-while-origin-is-https hazard recorded | whether to widen the credential (recommended: a narrow, revocable token) or keep this route permanently |
| `ADR-2026-016` **`Proposed`** | `harness ci` runs the harness's own stages in a consumer and misdiagnoses it; `default_pipeline()`'s docstring promises a consumer behaviour that does not exist | refuse clearly vs make it configurable — both touch the `harness.toml` schema |
| `ADR-2026-010`, `ADR-2026-012` | already recorded the budget unit and the validator dependency | the tokenizer choice |

`ADR-2026-016` is deliberately **`Proposed`**, not `Accepted`: it documents a defect
and the fix is undecided. An `Accepted` record describing unimplemented behaviour
would be a false record.

**Tests:** 513 without a database; coverage unchanged at 91.1%. Lint, format,
`mypy --strict`, `harness doctor`, `harness guards` and `harness ci` all clean.

## Follow-up: the handoff itself had gone stale

Refreshing `docs/design/REMAINING_WORK.md` for this session's handoff found it
described steps 1–3 as the state and steps 4–6 as "not started" — by then all six were
merged. A handoff that is wrong is worse than none, because it is trusted.

Corrected: the build-order table now lists all six plus the four capabilities built
beyond it; the historical step 4–6 narrative is replaced by a map to each step's design
note and decision record rather than a summary that would be a second copy to keep in
step; the decision table shows entry-location **closed** and adds the two items this
session surfaced; and the verification section no longer says "after step 3 merges".

### Added: Recorded the runtime dependency audit

*Audited and documented what the harness needs to run on any device or container, proving in a venv containing only PyYAML that no database, server or network is required and that every optional capability fails loudly with the fix in its message.*

- **ID:** `CHG-2026-015`  
- **Covers:** `MRB`

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

### Added: Session ledger — what was sent, proposed, decided and observed

*Implemented build-order step 5, recording each session as an append-only entry in git notes bound to its commit, with an optional Postgres mirror derived from the notes and proved rebuild-identical.*

- **ID:** `CHG-2026-014`  
- **Covers:** `MRB`

Implements build-order step 5 of `HARNESS_ARCHITECTURE.md` §9: *`git notes` +
Postgres; prompt, proposal, verdict, effect.*

```bash
harness ledger append --work-id MRB-M06-S01 --prompt-fingerprint <sha256> \
    --budget 4000 --unit word --proposal p.json --gate --effect applied
harness ledger list | show | verify | mirror | transport
```

## Where the record lives, and why

§5.3 gives the reasoning — git is already an append-only, content-addressed,
cryptographically ordered log with a distributed transport, and `git notes` adds
metadata without rewriting history. A record attached to a commit therefore
**survives a repository copy**, the property §10 names as the reason to prefer
notes over Postgres alone.

**A limitation, measured rather than assumed:** a `git notes` ref is **not** carried
by a plain clone or fetch. Records travel only when the ref is transported
explicitly, which `harness ledger transport` prints. This matters — a ledger that
appeared complete locally and silently lacked remote entries would be worse than no
ledger. The CLI prints the commands rather than executing them: pushing is a
separate authorised action.

## The prompt is recorded by reference

Step 3's fingerprint already binds the prompt bytes *and* the manifest of what is in
it, so the ledger stores the fingerprint, budget, unit and entry count — never the
text. Storing the prompt again would be a second copy to keep in step with the
compiler.

## The ledger records; it does not execute

§9 lists "effect" as a recorded field. The ledger has no executor, so it cannot
observe one: it records what the caller reports, and the default is
`not-observed` — the truthful value for a recorder that was not told. An invented
effect would be the ledger claiming knowledge it does not have.

Asserted from the source, not asserted in prose: every `subprocess` call is a
**literal git command** (so nothing built from a record can reach a shell), no
write/delete call exists outside git's own notes, and appending leaves the working
tree byte-identical — a ledger that dirtied the tree would make every later run
report a dirty tree.

## The mirror is derived, and provably so

Written from the notes and nothing else; resets first, so it is a rendering of the
current ledger rather than an accumulation — a record removed from the notes
disappears from the mirror rather than lingering as a fact git does not hold. Each
row stores both the queryable columns and the whole record, because storing only the
columns would make the invariant **unprovable by construction**. Drop it, rebuild
from the notes, digests identical — the step-1 pattern, reused.

A repository with no database still has a complete ledger.

## Two design faults found while building

1. **The mirror could never have proved its own invariant.** The first version
   stored only the queryable columns, so a rebuilt record could not equal the source
   record it came from. Caught before it shipped; the row now carries the whole
   record as canonical JSON alongside the columns.
2. **`mirror` was both a function and a submodule name.** `from harness.ledger
   import mirror` was ambiguous — a footgun for a caller. The function is now
   `write_mirror`.

**Tests:** 513 without a database; **585 with a live PostgreSQL**, coverage 91.1%.
Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and `harness ci`
all clean; CI matrix and the CI shape both pass.

### Added: Proposal schemas and effect gates — what may be proposed, and what is refused

*Implemented build-order step 4, a versioned JSON Schema for proposals plus gates that enforce the six rules architecture 7.1 enumerates, returning a three-valued verdict and never executing anything.*

- **ID:** `CHG-2026-013`  
- **Covers:** `MRB`

Implements build-order step 4 of `HARNESS_ARCHITECTURE.md` §9: *what the model may
propose, and how a proposal is checked*. The first step with a model in the loop —
and the one where the propose/dispose split becomes code rather than a diagram.

```bash
harness propose schema                  # the JSON Schema, for a provider
harness propose validate proposal.json  # structure only
harness propose gate proposal.json      # structure + every policy
```

## The §10.1 split, demonstrated rather than described

Structure is the provider's job; meaning is the harness's. §10.1 established that
constrained decoding enforces the schema at the sampling layer and that
**semantics are not enforced** — every adversarially steered model returned a
*valid* proposal.

The code shows the gap. This proposal is **fully schema-valid** and still refused:

```
$ harness propose validate …   → exit 0   (the provider would allow it)
$ harness propose gate …       → exit 2   (refused: `main` is a protected branch)
```

`1` (structurally invalid) and `2` (refused) are distinct exit codes for exactly
this reason: conflating structure with meaning hides the second case.

## The policies are the architecture's own rules

The `intent` enum is derived from the rules §7.1 already enumerates; each gate
cites the rule it enforces; a test asserts all six are covered, so a rule cannot
be dropped and a policy cannot be invented. The schema also enforces each intent's
required fields **conditionally**, so a `write_file` with no work packet is
structurally invalid — a stronger form of the rule than a gate that refuses it.
`additionalProperties: false` stops a key being smuggled in.

One mechanism the architecture does not enumerate but which makes
`never commit a secret` real: **a path may not escape the project root**.
Normalizing first is what closes `knowledge/../../.env`.

## Three-valued verdicts, and `not-checked` blocks

`permitted` / `refused` / `not-checked`, and `may_execute` is true only when every
gate is `permitted`. A session that declared no change manifest cannot be checked
against `one logical change per branch`, so a write reports `not-checked` and does
not proceed — the omission becomes visible instead of being assumed compliant.

The gate judges the branch a proposal **names**, not the branch the session is on:
creating `feat/x` is the intent that leaves a protected branch, while creating a
branch *called* `main` is refused. Refusing to *start* on a protected branch
remains the session guard's job (`ADR-2026-004`) rather than a second answer here.

## Nothing executes

There is no code path from a verdict to a mutation — asserted, not asserted-in-
prose: a test checks that neither module imports `os`, `subprocess`, `shutil`,
`socket`, `urllib` or `requests`, calls no write method, and that gating the same
proposal three times leaves the tree byte-identical.

## One new optional dependency

`jsonschema` via `.[propose]`, the standard implementation of the format §10.1
names. A hand-rolled subset would be a second definition of validity that drifts
from the provider's and fails at the boundary instead of in a test. A missing
validator is a **loud failure, never a silent pass**; the tests skip cleanly
without the extra (verified in a venv that omits it), and CI installs it.

## Two bugs found by the tests

1. **The gate permitted creating a branch called `main`.** It had special-cased
   `create_branch` on a protected branch, conflating the branch *named* with the
   branch *occupied*. Corrected, and the two cases are now separate tests.
2. **A manifest of `.` did not cover every path**, because `.env.example` is not
   prefixed by `"./"`. Corrected, with a test for the whole-project case.

**Tests:** 482 without a database; **548 with a live PostgreSQL**, coverage 91.5%.
Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and `harness ci`
all clean; CI matrix and the CI shape both pass.

### Changed: Parked build-order step 4 by owner instruction

*Recorded in the handoff that step 4 (proposal schemas + effect gates) is parked and must not be started without an explicit owner request, so a later session treats it as an instruction rather than a judgement call.*

- **ID:** `CHG-2026-012`  
- **Covers:** `MRB`

The owner parked step 4 and will request it explicitly when wanted. An unrecorded
"park" is exactly the transient instruction that the handoff document exists to
make durable: the next session reads the build order, sees step 4 marked as next,
and starts it.

`docs/design/REMAINING_WORK.md` §2 now carries a **PARKED** notice stating that an
agent must not begin step 4, speculatively prepare it, or prepare a branch for it,
and that starting it would be a violation rather than a judgement call. The
already-decided contract for the step is kept below the notice so the eventual
session builds against it instead of re-deriving it.

Nothing else changed: steps 5 and 6 remain not started, and the six
`DecisionRequired` items are unchanged.

Refs: HARNESS-REMAINING-001

### Added: Usage dashboard — run, record and view the harness in any repository

*Added a shipped usage dashboard that runs the harness's existing checks, records each run as a file so history accumulates and status changes are visible, and renders one self-contained HTML page with no server, no network and no new dependency.*

- **ID:** `CHG-2026-011`  
- **Covers:** `MRB`

A way to see, and keep seeing, how the harness behaves in a repository it is
installed into.

```bash
harness dashboard run       # run the checks, record the run, write .harness/usage.html
harness dashboard render    # re-render from recorded runs
harness dashboard history   # list recorded runs
```

## A viewer, not an actor

The request was for "a dashboard or control panel or visualization platform".
"Control panel" is the load-bearing word: controls imply the browser can act,
which would be a **second executor** in a system built on `ADR-2026-005` (the
harness executes, the model does not). So the dashboard runs the harness's
**existing** deterministic checks and nothing else, mutates only its own run
records and the rendered file, and has no control that could be misused. See
`ADR-2026-011`.

That also removes a server, a port, a network and a new dependency: the output is
one self-contained HTML file that opens over `file://`, offline, indefinitely. A
test asserts it contains **no** `http://`, `https://`, `src=`, `href=`, `@import`
or `<link`, so it cannot quietly acquire a CDN dependency.

## Checks are reused, not reimplemented

Every check comes from the module that already owns it — `Bundle.check`,
`validate_routing`, `validate_all`, `run_all`, the index store, the compiler's
unit. A dashboard reporting its own idea of health could disagree with
`harness doctor`, and two answers to one question is the drift this project exists
to avoid.

## `unknown` is a real outcome

The status is three-valued. An unreachable index is not a failing index; a branch
guard that **correctly** refuses a session on `main` must not be painted red, or
red stops meaning anything; a missing pytest is not a failing test. A boolean
would have to lie about at least one.

## History accumulates

One JSON file per run, following `ADR-2026-001` for the same reason: written once,
never edited. Timestamps sort lexicographically, so the newest run is the last
file without reading any; a same-second collision **adds** a file rather than
replacing one; and a malformed record is **reported, not skipped**, because a
missing entry is indistinguishable from a run that never happened.

The payoff is the **"Status changes between runs"** table — a check that was
passing and is now failing is the interesting event, and it is invisible in a
single run. Demonstrated in a fresh consumer: introducing a conformance error
produced `okf conformance: pass → fail` automatically, and reverting it produced
the reverse.

Provenance is recorded per run, including whether the working tree was **dirty** —
a run over uncommitted work is a different claim from a run over a commit.

## Injection found by a test

Report fields flow from repository content into HTML, so a project name is
untrusted input. A test caught a live injection: a name containing `</script>`
was interpolated raw into `<title>`. Every markup field is now HTML-escaped and
the embedded JSON escapes `<`, `>` and `&`; both are asserted.

## Verified

- 33 dashboard tests; `collect()` is reproducible with an injected `now`.
- Rendered and inspected in a browser for both the harness itself and a fresh
  consumer (`JOB-A01-B002` grammar, `kb/` bundle, `specs/` docs).
- Self-containment, escaping, append-only history, collision handling, malformed
  records and transitions all asserted.
- `.harness/` is gitignored: telemetry is local, and committing it would make the
  dashboard report its own output as a dirty tree.

**Tests:** 415 passing without a database; **481 with a live PostgreSQL**,
coverage 91.4%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards`
and `harness ci` all clean.

### Added: Recorded the remaining build order and the open decisions

*Added docs/design/REMAINING_WORK.md, a durable handoff recording which build-order steps are done, the step 4-6 contract, five DecisionRequired items that must not be guessed, and the environment traps that have already cost time.*

- **ID:** `CHG-2026-010`  
- **Covers:** `MRB`

Steps 1–3 of the build order are done; steps 4–6 are not. A handoff that lived
only in a session transcript would be lost, so the state is recorded as a
repository artifact.

## What it records

- **Which steps are done**, which PR landed each, and the entry point each
  provides.
- **The step 4 contract** — the first step rated Medium risk, and the one that
  puts a model in the loop. The constraint is already fixed: `ADR-2026-005` gives
  the harness execution authority and the model proposals only, and §10.1's
  experiment showed schema enforcement is native while **semantics are not**, so
  the effect gates are where the real checking lives.
- **Five `DecisionRequired` items** that must not be answered with a plausible
  default: the budget unit, the PostgreSQL version, the entry-location
  contradiction, the `workflow` scope, and Postgres locality.
- **The traps**, because each has already cost time: location resolved from
  `Path(__file__)` (five occurrences), `MRB_TEST_DSN` falling back to a real DSN,
  `harness ci` gating on session guards, the `gh`-SSH-vs-https credential
  mismatch, an unreadable `~/.ssh/known_hosts`, and the general rule that a green
  local run is not evidence.

Verified against the repositories rather than recalled: the merged PR numbers,
the entry IDs, the scope list from `gh auth status`, and the `harness.toml`
`decisions` path.

Refs: HARNESS-REMAINING-001

### Added: Prompt compiler — a work item in, a bounded prompt and a fingerprint out

*Implemented build-order step 3, compiling a task ID plus a caller-supplied budget into a deterministic prompt with a SHA-256 fingerprint that binds its content; over-budget and blocked work items are refused rather than truncated.*

- **ID:** `CHG-2026-009`  
- **Covers:** `MRB`

Implements build-order step 3 of `HARNESS_ARCHITECTURE.md` §9: *task ID +
selection + budget → prompt + fingerprint*. Deterministic — no model, no clock,
no network.

## What it does

Selection comes from `harness.routing.resolve`; text comes from the same
`git archive` materialization step 1 introduced, so the prompt is a **pure
function of a committed revision**. `harness compile <work-id> --budget N` prints
the prompt on stdout and the fingerprint on stderr, so a caller can capture either
without the other. `--json` carries both; `--manifest` carries the audit record
without the text.

## The fingerprint is the §3 dashed edge, made executable

The architecture calls the pre-call fingerprint *load-bearing*: without it a
session cannot be reproduced and "deterministic" is an unevidenced claim. The
digest covers the prompt text **and the manifest** of which documents are in it —
concept id, path, title, read budget, trust tier, status, staleness, coverage and
per-entry size.

Hashing the text alone would let a same-length document be substituted without the
digest changing. A test asserts the structure binds.

## No invented threshold

`--budget` is **required with no default**. No authoritative document fixes a
value, and a default would silently become part of every fingerprint. The unit is
an exact **word** count, named in `harness.compile.tokens.UNIT` — deterministic
and provider-independent, which is what a reproducible compiler needs. It is not
called a "token", because a token depends on the model's tokenizer and would make
the budget provider-specific. Adopting a tokenizer is recorded as
`DecisionRequired` in `ADR-2026-010`.

The budget bounds admissibility, not content, so it does **not** enter the
fingerprint: a generous and a tight budget compile the same prompt.

## Refusal, not truncation

| Condition | Exit |
|---|---|
| blocked | `3` |
| nothing covers the chain | `4` |
| over budget | `5` |
| usage error | `2` |

Over budget is all-or-nothing on purpose. Dropping documents would be a **false
claim** about what binds the work item, and the failure is invisible — the model
would answer confidently from partial context. `harness context` remains available
for discovery. `--defining` is passed through, so a concept whose `do_not_use_for`
names a state the caller intends to define appears in the manifest as **excluded**
rather than vanishing.

## Verified

- 35 compiler tests and 9 CLI tests: determinism, fingerprint binding, every
  refusal path, exclusion, manifest.
- Same revision compiles byte-identical text and fingerprint; an uncommitted edit
  changes neither; a committed edit changes both.
- Real consumer corpus: `MRB-M06-S01` compiles 10 documents / 2582 words /
  fingerprint `395fe52f…`, **identical across runs**; `MRB-M06-S07` refuses with
  exit 3 naming `DESIGN-RUBRIC-01`, `EVID-AI-HW-01`, `IMG-DIM-01`.
- A malformed work identifier is reported as a usage error rather than escaping as
  an uncaught `OkfError` — found by a test, fixed.

**Tests:** 382 passing without a database; **448 with a live PostgreSQL**,
coverage 91.3%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards`
and `harness ci` all clean.

### Added: Query API — lookups answered by SQL, not by reading files

*Implemented build-order step 2, a query surface over the derived index; list-valued scope fields are indexed element-wise so a scope query cannot silently select child scopes, and the SQL answers are tested against the Python resolver.*

- **ID:** `CHG-2026-008`  
- **Covers:** `MRB`

Implements build-order step 2 of `HARNESS_ARCHITECTURE.md` §9: *the lookup surface
that replaces file-reading*. Most agent questions are lookups wearing a costume,
and each one answered by code removes tokens and a hallucination surface.

## Commands

| Command | Question it replaces |
|---|---|
| `query documents` | list the corpus |
| `query show <id>` | what does this document say it is? |
| `query search <text>` | which document mentions this? |
| `query links <id> [--direction in\|out]` | what does this depend on? |
| `query touching <work-id> [--field …]` | which documents cover this scope? |
| `query blocked <work-id>` | is this blocked? |
| `query stops [--state …]` | which work items are blocked, and by what? |
| `query decisions [--status …]` | what is decided? |
| `query gaps [--state …]` | what does the gap register hold? |

All accept `--json`; `--dsn` overrides the environment.

## The schema decision

Step 1 stored `covers` as JSON text, so a scope query could only be a substring
match — and `%MRB-M06%` also matches `MRB-M06-S07`. That silently over-selects
every child scope: an agent would be handed documents it believes bind its work
item, with nothing in the output saying otherwise.

List-valued routing fields are now projected **one row per element** into
`document_field_items`, so a scope query is an exact join. `MRB-M06` selects only
documents that name `MRB-M06`. Over-selection is structurally impossible rather
than merely tested for. See `ADR-2026-009`.

The step 1 invariant is untouched: `read_model` still reconstructs from
`document_fields`, so the digest and the rebuild-identity test are unchanged.
`INDEX_SCHEMA_VERSION` is 2.

## Cross-checked, not assumed

`blocked` and `touching` restate logic `harness.routing.resolve` already
implements. A test compares the SQL answers with `resolve_context` over the same
committed model, and a divergence fails — the Python resolver is the reference,
because that is what an agent actually runs.

Verified against a **real consumer** (`mr_bera`, 34 documents, 17 registry
tables) on three work items. The SQL and Python answers matched exactly:

| Work item | Both report |
|---|---|
| `MRB-M06-S07` | `DESIGN-RUBRIC-01`, `EVID-AI-HW-01`, `IMG-DIM-01` |
| `MRB-M06-S14-C02` | `CONTROL-STORE-01` |
| `MRB-M02` | none |

`query stops` on that corpus returns **12** `BlockedOwner` rows in one query —
the join §5.2 says belongs in SQL, which previously meant reading every `Unknown`
concept and correlating by hand.

## Honesty in the exit codes

Without a DSN, a query exits **3** rather than reporting "nothing applies". An
unreachable index and an empty index are different things; conflating them would
hand an agent a false clean bill of health. Usage errors are validated *before* a
connection is attempted, so a mistyped field name reports the field, not a
connection failure.

## A safety defect found and fixed

The database fixtures fell back to `MRB_HARNESS_DSN` — the same variable that
points at a real index — and they call `reset`, which drops the tables. A test run
against that variable therefore **destroyed an indexed consumer project**, which
is exactly what happened once during development. The fixtures now require
`MRB_TEST_DSN` with no fallback, and a test run with only `MRB_HARNESS_DSN` set
leaves the real index intact (verified: all 12 rows survived).

## CI now runs a database, because the coverage floor said so

The first CI run of this branch failed **all three test jobs while every test
passed** (`338 passed, 66 skipped`). The cause was the coverage floor:

```
FAIL Required test coverage of 80.0% not reached. Total coverage: 79.02%
```

Requiring a separate test DSN also meant CI skipped the whole derived-store layer
— ~350 statements in the modules this step adds — so the floor was being enforced
against code CI never ran. Both symptoms have one cause.

The `test` job now runs a `postgres:16` service and installs the `postgres`
extra, so the index and query tests execute instead of skipping. Coverage rises
from 79% to **91%** as a side effect, which is the honest measure: the code is
now actually exercised rather than excluded.

Two alternatives were rejected. Silencing the derived-store modules in the
coverage config would raise the number by measuring less — the opposite of what a
floor is for. Lowering the floor below 80% would make the number pass while
leaving the layer untested. Neither makes anything more correct.

Verified locally against both DSN states before pushing: **338 passed** without a
database, **404 passed / 91.16%** with one. The rehearsal (`harness ci`) runs no
coverage gate, so it is green either way.

**Tests:** 338 passing without a DSN; **404 with a live PostgreSQL**, coverage
91.2%. Lint, format, `mypy --strict`, `harness doctor`, `harness guards` and
`harness ci` all clean.

### Fixed: The build rehearsal no longer fails on the default branch

*harness ci ran the session guards, which refuse a protected branch by design, so the build was red on main while every build check passed; the rehearsal now asserts tree properties only.*

- **ID:** `CHG-2026-007`  
- **Covers:** `MRB`

`harness ci` reported `RESULT: FAILED — selfcheck` when run from `main`, while
wheel build, lint, format, `mypy --strict`, the full test suite, OKF conformance,
routing invariants, entry schema, generated-index currency and commit convention
all passed.

## Cause

The self-check stage invoked `harness guards` as a "branch not stacked" check.
`harness guards` is **session activation**, and it correctly refuses a protected
branch (ADR-2026-004). The build was therefore red because of *where* it ran, not
what it contained.

The fault was categorical: a session precondition was wired into a build
verification, making the build's result depend on branch position. Taken to CI —
which runs on `main` by definition — it would have failed every push to the
default branch.

## Fixed

The stage now asserts only properties of the tree: OKF conformance, routing
invariants, entry schema, generated-index currency, the resolver exit-code
contract, and commit convention. Session activation stays where ADR-2026-004 put
it — a step an agent runs before doing work. Nothing is less guarded; branch
policy is still enforced at session start, which is the only moment it is
actionable.

Two tests pin the separation so a later edit cannot silently re-add the step.
The reason is stated in the stage list itself.

**Before:** `harness ci` on `main` → exit 1. **After:** exit 0, with the same
checks passing.

Refs: ADR-2026-008

### Fixed: The local CI rehearsal runs in the invoking repository again

*harness ci resolved its root from the installed package directory, so 8 of 12 stages failed while its parity check reported success having read nothing; stages now run in the invoking repository and parity reads the workflow.*

- **ID:** `CHG-2026-006`  
- **Covers:** `MRB`

`ci/rehearse.py` was the last module still resolving its own location
(`Path(__file__).resolve().parent.parent`), which points at the installed package
(`.../src/harness`) rather than the repository the command was run in. Its
siblings had already been corrected; the runner was missed.

## Observed, before the fix

From the harness repository root:

```
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
[parity] local stages vs .github/workflows/ci.yml
  missing locally: none      <-- reported success while reading nothing
RESULT: FAILED — package, typecheck, test, selfcheck
```

Eight of twelve steps failed. The parity check was the worse fault: it compared
the pipeline against a job list it had not parsed, so a green local run would
have meant nothing.

## Fixed

- `repo_root()` resolves `Path.cwd()`, matching `guards/session.py`;
  `run_stage` executes there.
- `check_parity` reads the workflow file, and a parity failure now fails the run.
- The `selfcheck` stages name existing commands; `mypy src` matches `ci.yml`; the
  dead `tools/*.py` references are gone.
- `Step.ok_exit_codes` records that a deliberate non-zero exit is a passing
  check, so the rehearsal can assert the `harness context` exit-code contract.

Result: `RESULT: PASSED`, `parity: every CI job has a local stage`.

## Found while fixing it

With the runner correctly executing in the invoking repository, a test that
called `main(["ci"])` from inside pytest recursed forever — the `test` stage runs
pytest. The test now builds a trivial pipeline from the module's own stages and
asserts the runner drives it, without re-entering the suite.

**Tests:** regression tests pin the root and the parity read.

### Added: Extraction and a derived index that rebuilds identically from git

*Implemented build-order step 1 — committed git bytes are extracted with the tested OKF reader into a normalized model with a stable digest, loaded into PostgreSQL as a derived index, and proven rebuild-identical by dropping the database and rebuilding from git.*

- **ID:** `CHG-2026-005`  
- **Covers:** `MRB`

Implements build-order step 1 of `HARNESS_ARCHITECTURE.md` §9: *extraction + index
— parse frontmatter/tables into Postgres; prove rebuild-from-git is identical.*

## What was built

**Extraction** (`harness/extract/`) — a pure function from committed bytes to a
normalized model:

- `model.py` — frozen `Document` / `RegistryTable` / `IndexModel` and
  `model_digest`, SHA-256 over a canonical JSON rendering. No timestamps, no row
  ids, no insertion order, so the same revision always serializes the same.
- `documents.py` — body headings, resolved internal links, and markdown tables.
  Parsing is **reused** from `harness.okf.reader`, not reimplemented.
- `source.py` — `git archive <rev>` materialized into a temporary tree, then read.
  Extraction therefore sees committed content only.

**Index** (`harness/index/`) — a derived PostgreSQL store. `reset` drops and
recreates the tables; `write_model` writes a model; `read_model` reconstructs one
**from the rows alone**, never touching the filesystem.

**CLI** — `harness index build | verify | status`, returning 3 when PostgreSQL is
unreachable, in keeping with the existing exit-code contract.

## The invariant

The test drops the tables, rebuilds from git, and requires the two models'
digests to be identical *and* compares them table-by-table. It also asserts the
model is non-empty and that a committed change **breaks** the equality — without
those, it could pass while indexing nothing. A hand-run negative control
corroborated it: corrupting one stored field changed the digest
(`73c167aa…` → `f1b349f5…`).

Verified against a real PostgreSQL, not only against the store in isolation.

## Notes

- **A defect CI caught that a local run could not.** The git-backed fixtures
  initially ran `git commit` relying on the host's global identity. That exists on
  a developer machine and not on a runner, so the tests passed locally and failed
  in CI with `Author identity unknown` (exit 128) on all three Python versions.
  The fixtures now supply an identity explicitly (a local `user.name`/`user.email`
  plus the environment). Reproduced with `GIT_CONFIG_GLOBAL=/dev/null
  GIT_CONFIG_SYSTEM=/dev/null HOME=<empty>`, which is now the shape this work is
  verified against.
- `psycopg` stays an optional extra, the index tests skip cleanly without a DSN,
  and no PostgreSQL version is asserted — no authoritative document fixes one.
- Registry files are read from `[registries.*]` in `harness.toml`; the harness
  never guesses which documents are registries.
- Paths resolve from the invoking directory. Resolving a caller's context from
  the library's own location is a defect this repository has hit repeatedly.

**Tests:** 329 passing (15 skipped without a DSN); 344 passing against a live
PostgreSQL, coverage 87.9% against an 80% floor. Lint, format, `mypy --strict`,
`harness doctor` and `harness ci` all clean.

## 2026-10-10

### Fixed: Git commands run in the invoking repository, not the package's directory

*Both the commit-convention check and the guards resolved their repository root from the package's own location, so run from a consumer they failed or operated on the wrong repo.*

- **ID:** `CHG-2026-004`  
- **Covers:** `MRB`

`commits.py` and `guards/session.py` resolved their repository root from
`Path(__file__).resolve().parent.parent` — the harness's *installation*
directory. Run from a consumer, `git` then executed there and failed with
`fatal: not a git repository`.

This is the third defect of the same class, and the pattern is worth naming:
**a library must never resolve the caller's context from its own location.**
The other two were the generated-index output path (wrote into the harness repo)
and `validate_all()`'s default directories (silently validated a consumer as
empty).

It reached CI because the harness's own tests always run from the harness's own
directory, where the two paths coincide. A regression test now asserts the root
from a *different* directory, which is the only condition that exposes it.

278 tests, 89.4% coverage.

### Fixed: Wire the missing subcommands, and stop writing into the wrong repository

*Four capabilities were unreachable from the CLI after the entry points were consolidated, and generated indexes were written into the harness repo instead of the invoking project.*

- **ID:** `CHG-2026-003`  
- **Covers:** `MRB`

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

### Changed: Framework documentation moved into the harness repository

*Moved the harness design, format and research documentation plus five framework ADRs out of the consuming repository.*

- **ID:** `CHG-2026-002`  
- **Covers:** `MRB`

The harness's own documentation now lives with the harness:

- `docs/design/HARNESS_ARCHITECTURE.md` — the design
- `docs/design/OKF_MODULE_SYSTEM.md` — the bundle format and exit-code contract
- `docs/design/RESEARCH_DOSSIER.md` — prior art and the reproduced experiments
- `docs/decisions/ADR-2026-001..005` — the decisions that govern the framework

**Two ADRs stayed behind deliberately.** `ADR-2026-006` (trunk-based
development) and `ADR-2026-007` (Conventional Commits) are decisions a consuming
repository makes about *its own* delivery. Moving them would have stranded that
repository's rules in a project it does not own.

Three defects were found while moving:

1. **`validate_all()` ignored configuration.** Its directory defaults were
   module-level constants pointing at one fixed layout, so a repository keeping
   its entries elsewhere was silently validated as *empty* — zero entries, zero
   problems, which reads like success. The defaults now come from `harness.toml`.
2. **The harness's own config pointed at the wrong place** after the move, so
   `doctor` reported 1 entry instead of 6.
3. **Stale cross-references** inside the moved documents pointed at paths that no
   longer existed.

Also retargeted: `OKF_MODULE_SYSTEM.md` documented a set of scripts
(`tools/okf.py`, `tools/okf_context.py`). In the harness those are a package with
one entry point, so its commands now read `harness context`, `harness conform`.

Verified: 250 tests, 80.7% coverage, lint and mypy clean, and `harness doctor`
reports the harness repository clean with 6 entries.

### Added: Initial harness with a config layer

*Extracted the generic routing, entry, guard and CI tooling into a project-agnostic package driven by harness.toml, with 250 tests.*

- **ID:** `CHG-2026-001`  
- **Covers:** `MRB`

Extracted the generic half of the MrBera tooling into an importable framework.

The decisive measurement was coupling: `okf.py`, `local_ci.py` and
`check_commit_convention.py` had **zero** references to MrBera, while
`routing.py` and `validate_routing.py` had 9 and 22. The split followed that
line rather than being imposed on it.

New: `harness/config.py`. Everything project-specific — the identifier grammar,
document locations, registry names, branch policy — is now read from
`harness.toml`. Verified against a consumer that names work items differently
(`TASK-P001-T0002`), which the hardcoded grammar could not have routed.

Three defects were found during the port, each by a test:

1. **Parent chain truncated.** Segment splitting grouped tokens in pairs,
   producing bogus segments like `M06-S07` and stopping the chain at
   `MRB-M06-S07` instead of `MRB-M06` — silently under-selecting context.
2. **`MRB` alone accepted.** The grammar allowed the bare prefix, which names a
   system rather than a unit of work and routes to an empty chain.
3. **Repo-root resolved wrong.** `parents[2]` pointed at `src/`, so the CLI read
   a different tree than a caller passing explicit paths, and `--check` reported
   drift that did not exist.

Four duplicate `main()` entry points were removed. Each shadowed `cli.py` and was
never reached, which is why they showed as uncovered; removing them raised
coverage from 69% to 80%.

250 tests, coverage 80.5%, lint and format clean, and the harness passes its own
`harness doctor`.
