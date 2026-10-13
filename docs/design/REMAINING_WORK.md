---
id: HARNESS-REMAINING-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [HARNESS_ARCHITECTURE.md, EXTRACTION_INDEX.md, QUERY_API.md, PROMPT_COMPILER.md]
do-not-use-for: [commerce-truth, fulfilment-truth, editorial-policy, release-plane]
read-budget: must-read
---

# Remaining work

> ID: HARNESS-REMAINING-001
>
> Status: **Live handoff** — the state of the build order, and what is next.
>
> Authority: a design document. It records status and open questions. It creates
> no decision. Every claim below was observed, not inherited.

---

## 1. Where the build order stands

`HARNESS_ARCHITECTURE.md` §9 lists six components. **All six are implemented and
merged, and `main` is green.** A further six capabilities were built beyond the build
order, because each closed a gap the project had recorded against itself.

<!-- harness:handoff-facts:start -->
| Fact | Value |
|---|---|
| Derived by | `mr-bera-harness 0.1.0`, via `tools/refresh_handoff.py` |
| OKF concepts | 22 |
| Entries | 42 (0 problem(s)) |
| Test modules | 23 |
| Provenance declarations | 2 |
| Commit types accepted | 11 |
<!-- harness:handoff-facts:end -->

| # | Component | State | Landed |
|---|---|---|---|
| 1 | Extraction + index | **Done** | PR #2 → `ADR-2026-006`, `CHG-2026-005` |
| 2 | Query API | **Done** | PR #4 → `ADR-2026-009`, `CHG-2026-008` |
| 3 | Prompt compiler | **Done** | PR #5 → `ADR-2026-010`, `CHG-2026-009` |
| 4 | Proposal schemas + effect gates | **Done** | PR #9 → `ADR-2026-012`, `CHG-2026-013` |
| 5 | Session ledger | **Done** | PR #10 → `ADR-2026-013`, `CHG-2026-014` |
| 6 | Instruction → prompt | **Done** | PR #14 → `ADR-2026-018`, `CHG-2026-018` |

Beyond the build order:

| Capability | State | Landed |
|---|---|---|
| Usage dashboard | **Done** | PR #7 → `ADR-2026-011`, `CHG-2026-011` |
| Runtime dependency audit | **Done** | PR #11 → `CHG-2026-015` |
| Purpose and framing | **Done** | PR #13 → `CHG-2026-017`, `docs/PURPOSE.md` |
| Code provenance | **Done** | PR #15 → `ADR-2026-019`, `CHG-2026-019` |
| README staleness | **Done** | PR #17 → `CHG-2026-020` |
| Generated handoff facts | **Done** | `ADR-2026-020`, `CHG-2026-021` |

What each build-order step provides:

| Step | Provides | Entry point |
|---|---|---|
| 1 | committed git → normalized model → derived Postgres index, proven rebuild-identical | `harness index build\|verify\|status` |
| 2 | lookups answered in SQL; element-wise scope matching | `harness query …` |
| 3 | work item + budget → deterministic prompt + content-bound fingerprint | `harness compile <id> --budget N` |
| 4 | a versioned proposal schema and gates enforcing §7.1's rules; executes nothing | `harness propose schema\|validate\|gate` |
| 5 | session records in `git notes`, bound to commits, with a derived mirror | `harness ledger …` |
| 6 | instruction → work item, or a clarification request; calls no model | `harness intent resolve` |
| — | code → the decision that produced it, checked by hash | `harness provenance check\|map\|index` |

## 2. What has already been built

Every build-order step has its own design note and decision record; read those rather
than a summary here, which would be a second copy to keep in step. The map:

| Step | Design note | Decision |
|---|---|---|
| 1 Extraction + index | `EXTRACTION_INDEX.md` | `ADR-2026-006` |
| 2 Query API | `QUERY_API.md` | `ADR-2026-009` |
| 3 Prompt compiler | `PROMPT_COMPILER.md` | `ADR-2026-010` |
| 4 Proposal gates | `PROPOSAL_GATES.md` | `ADR-2026-012` |
| 5 Session ledger | `SESSION_LEDGER.md` | `ADR-2026-013` |
| 6 Instruction → prompt | `INTENT_RESOLUTION.md` | `ADR-2026-018` |
| Usage dashboard | `DASHBOARD.md` | `ADR-2026-011` |
| Runtime dependencies | `RUNTIME_DEPENDENCIES.md` | `CHG-2026-015` |
| Code provenance | `CODE_PROVENANCE.md` | `ADR-2026-019` |
| Purpose and framing | `PURPOSE.md` | `CHG-2026-017` |
| Generated handoff facts | `REMAINING_WORK.md` §1 (marked region) | `ADR-2026-020` |

## 3. What remains, and what is genuinely undecided

**The build order is complete.** What remains is not a next component; it is the
`DecisionRequired` list in §5. The one item that was left deliberately open —
`ADR-2026-017`'s status — is now closed: it is `Superseded` by `ADR-2026-019`, which
implemented the capability it proposed (decision 7 below).

## 4. Open decisions — do not guess these

Each is `DecisionRequired`. None may be supplied by a plausible default.

| # | Decision | Why it is blocking | Where recorded |
|---|---|---|---|
| 1 | **Budget unit** — is a model tokenizer adopted? | the compiler uses an exact word count today; adopting a tokenizer changes what every recorded budget means and makes old budgets incomparable | `ADR-2026-010` |
| 2 | **PostgreSQL supported version range** | no authoritative document fixes one, so none is asserted; the `postgres:16` image in CI is a **test fixture, not a support claim** | `ADR-2026-014` |
| 3 | ~~Entry location~~ | **CLOSED** — the generated header was hardcoded; it now reads the configured path | `CHG-2026-016` |
| 4 | **`workflow` scope for agent sessions** | no `workflow` scope, so `.github/workflows/**` is pushed over SSH with the owner's key. Recommendation: a narrow, revocable fine-grained token — **not** widening this one, which carries `admin:public_key` | `ADR-2026-015` |
| 5 | **Postgres locality / index lifecycle** | status quo recorded: **rebuild-on-demand**, no service. Locality and any future service remain the owner's | `ADR-2026-014` |
| 6 | **`harness ci` has no consumer pipeline** | **`Proposed`, not fixed**: in a consumer it runs the harness's own stages and misdiagnoses the consumer as broken. Refuse clearly vs make it configurable. See §5.1 | `ADR-2026-016` |
| 7 | ~~`ADR-2026-017` status~~ | **CLOSED** — 017 was `Proposed` while `ADR-2026-019` implemented it. Resolved by supersession: 019 records `supersedes: [ADR-2026-017]` and 017 is `Superseded`, so 017 keeps the proposal it made and the current instruction is unambiguous | `ADR-2026-019` |
| 8 | **`harness dashboard run` guard scope** | the guard check inspects the *live repository* regardless of the `branch` argument, so it can report a failure the caller never asked about — and one test is environment-dependent as a result. See §5.2 | open |

### 4.1 A consumer test found what the unit tests could not

A throwaway consumer repository was built to share nothing with `mr_bera` — a
`TASK` prefix with grammar `P/T`, widths `3,4`, bundle at `kb/`, docs at
`specs/`. Every command was exercised against it. Steps 1–3 passed in full: the
config layer, the resolver's `0/2/3/4` contract, `index verify` rebuilding
identically before and after a commit, all nine queries, all compile paths
including the `3` and `5` refusals, and `entries generate` writing into the
consumer with the harness repository left untouched.

It also found the defect in decision 6 above, which no unit test could have: the
tests run *inside* the harness repository, where the harness's own pipeline is
correct.

## 5. Housekeeping and environment traps

### 5.1 `harness ci` is not project-agnostic

`harness ci` runs the harness's own pipeline wherever it is invoked — wheel build,
`mypy src`, the `selfcheck` stages — so in a consumer it fails with a message that
implies the consumer is broken:

```
$ harness ci      # in a consumer
  FAIL  wheel build        Directory '.' is not installable ... no pyproject.toml
  FAIL  pytest             file or directory not found: tests/
  FAIL  okf conformance    no harness.toml in .../src/harness
RESULT: FAILED — package, typecheck, test, selfcheck
```

This is the same class as the four location defects already fixed: the library
answering a question about its own context rather than its caller's. It also
contradicts `ci/rehearse.py`'s own docstring ("A consumer defines its own
`Pipeline` directly; this default exists only so the harness can dogfood itself"),
so today the documented consumer behaviour does not exist.

It is left unfixed on purpose: the correct behaviour is a decision, not a
correction. Either the command errors clearly when no pipeline is configured for
the project, or `harness.toml` gains a way to declare one. Both are reasonable and
the choice has consequences for the config schema.

Impact is bounded: CI runs `ci.yml`, not `harness ci`, and no shipped capability
depends on it. Everything below was observed in a fresh consumer repository —
see §5.1.

### 5.2 `harness dashboard run` reports a guard failure the caller did not ask about

`_guards` in `dashboard/report.py` calls `run_all(branch, …)`, but the `base-branch`
guard inside it inspects the **live repository** regardless of the `branch` argument:
`guard_base_branch_is_default` resolves `origin/main` and the merge-base from the
checkout, not from the branch it was handed.

Two consequences, both observed:

- `collect(config, branch="feat/x")` can report `session guards: fail` because the
  *working copy* is behind `main` — a fact unrelated to the branch being asked about.
- The test `test_guards_on_a_feature_branch_pass` therefore depends on the state of
  the repository it runs in. It passed only because the checkout was clean at the
  time; an uncommitted merge made it fail.

Not fixed here because the fix is a semantics question, not a typo: either
`guard_base_branch_is_default` must accept the branch and the base to compare, or
`_guards` must pass a synthetic base and say so. The `branch` argument's contract
needs deciding first. Impact is bounded — it is a reporting inaccuracy in the
dashboard, not a wrong permit or refusal — but it makes one test environment-
dependent, which is the hazard this repository keeps paying for.

### 5.3 Traps already paid for
Recorded because each has already cost time:

- **Four merged remote branches** remain on GitHub (`feat/extraction-index`,
  `fix/ci-selfcheck-branch-scope`, `feat/query-api`, and any earlier). Deleting
  them is an owner action.
- **Credential mismatch.** `gh auth status` reports *"Git operations protocol:
  ssh"* while `origin` is an **https** URL with a stale entry in
  `~/.git-credentials`. `gh` reports scopes `admin:public_key, gist, read:org,
  repo` — **no `workflow`**.
- **`~/.ssh/known_hosts` is unreadable to the agent process**, so git-over-ssh
  fails host-key verification unless `UserKnownHostsFile` is supplied. Fix on the
  host with `ssh-keyscan github.com >> ~/.ssh/known_hosts`.
- **`MRB_TEST_DSN` must never fall back to `MRB_HARNESS_DSN`.** The test fixtures
  call `reset`, which drops tables; a fallback destroyed a real index once.
- **A library must not resolve its owner's context from its own location.** This
  defect has appeared five times (`guards/session.py`, `entries/commits.py`,
  `entries/generator.py`, `ci/rehearse.py`, and `ci/rehearse.py` again via the
  parity check). Resolve from `Path.cwd()`, never `Path(__file__)`.
- **`harness ci` cannot pass on `main` if the session guards are a build stage** —
  settled by `ADR-2026-008`. The two gates answer different questions.
- **`harness ci` is not project-agnostic** — it runs the harness's own stages in a
  consumer. Recorded as `Proposed` in `ADR-2026-016`; it will misdiagnose a consumer
  as broken until the owner chooses the fix.
- **A generated file must not state a location it was not told** — the header text
  was hardcoded. Fixed; the renderers now read the configured path.
- **"Works locally" is not evidence.** CI caught two defects a green local run
  could not: a missing git identity in fixtures, and a coverage floor enforced
  against code CI never ran.

## 6. How to verify the current state

```bash
cd <repo>
pip install -e ".[dev,postgres,propose]"       # propose/postgres are optional extras
export MRB_TEST_DSN="postgresql://…/a_throwaway_db"   # NEVER the real MRB_HARNESS_DSN

harness doctor                                  # conformance, routing, entries
harness guards                                  # refuses a protected branch, by design
harness provenance check                        # code -> decision links verify
python -m pytest -q                             # without a database
python -m pytest -q                             # with MRB_TEST_DSN set
harness ci --workflow .github/workflows/ci.yml  # rehearsal + parity
python tools/refresh_handoff.py --check         # is this document current?
```

Expected on `main`: `doctor` **clean**, `guards` **fails on `main` by design**,
`provenance check` exit 0, tests green, coverage above the 80% floor, `harness ci`
**PASSED**, `refresh_handoff.py --check` exit **0**.

**`MRB_TEST_DSN` must be a throwaway database.** The fixtures call `reset`, which
drops tables; a fallback to `MRB_HARNESS_DSN` once destroyed a real index.

### 6.1 The handoff's own facts are generated

`tools/refresh_handoff.py` rewrites **only** the region between the
`<!-- harness:handoff-facts:start -->` and `<!-- harness:handoff-facts:end -->` markers
in §1, deriving every value through the harness's own library rather than restating it
(`ADR-2026-020`). Everything outside the markers is a human edit and is never touched.

| Invocation | Contract |
|---|---|
| `python tools/refresh_handoff.py` | refresh the region; `0` |
| `python tools/refresh_handoff.py --check` | `0` current · `1` **stale** · `2` no markers |

The region holds **only facts that are functions of the committed content**. Two
categories are deliberately excluded, each with a failure attached:

- **The revision and the dirty flag.** A committed file cannot contain its own commit's
  hash, so a region naming `HEAD` would be stale the instant it was committed and
  `--check` could never return `0`. A handoff that names a revision must write it by
  hand — which is honest, because it is then visibly a claim a person made.
- **The test pass and skip counts.** They describe the *environment*: this same commit
  reports a different pair with and without `MRB_TEST_DSN`, so generating them would
  make `--check` flap between a laptop and CI. Test results live in the changelog entry,
  with their provenance.

**Automatic cleanup.** A scheduled session (see §6.2) runs `--check` and, when it exits
`1`, refreshes the region, re-reads the narrative around it, and — if a fact has moved
in a way that changes the story — updates the prose and opens a draft PR. The schedule
is a maintenance trigger, not an authority: nothing it produces is merged without a human.

**Stated limit, because a generated region invites over-trust:** the script proves the
region matches the repository's derivations. It cannot prove the narrative above it is
true — the v1.0 staleness was prose, and no marker catches prose.

### 6.2 The scheduled handoff refresh

Configured as an agent automation on the Local Agent Host, **not** in CI: CI validates a
candidate, whereas this repairs a document, and the two are different questions
(`ADR-2026-008` makes the same distinction for the guards).

| Where | Value |
|---|---|
| Automation | `Handoff fact refresh (automatic cleanup)` |
| Host | Local Agent Host (VS Code agent automations) |
| Schedule | weekly, Monday 09:00 local |
| Target | this repository, isolated in a worktree off `main` |

Its prompt instructs the session to branch from `main`, run `--check`, refresh and
verify on exit `1`, correct only narrative the repository can justify, and open a
**draft** PR. It is configured on the host rather than stored in this repository, so it
is not reviewable here — the script it runs, and the contract above, are.

An automation is a **trigger**, not a permission: it inherits the branch rules, it cannot
merge, and a human reviews its PR like any other. If the host is unavailable the
mechanism degrades to the manual command in §6.1, which is why the script is the
load-bearing part and the schedule is only the convenience.

## 7. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Recorded the build-order state after steps 1–3, the step 4–6 contract, five open decisions and the environment traps. |
| v1.1 | 2026-10-13 | Added decision 6 (`harness ci` is not project-agnostic) and §4.1, the fresh-consumer test result that found it. |
| v1.2 | 2026-10-13 | Marked step 4 **parked** by owner instruction. |
| v1.3 | 2026-10-13 | Closed the blocker list: two mechanical defects fixed, four status-quo ADRs (`014`–`016`) recorded. |
| v1.4 | 2026-10-13 | Recorded §5.2: the dashboard's guard check inspects the live repository, making one test environment-dependent. |
| v2.0 | 2026-10-13 | **All six build-order steps are done.** Replaced the historical §2–§4 with a map to each step's design note and decision, refreshed the decision table (entry-location closed; two new items), and corrected the verification section. |
| v2.1 | 2026-10-13 | §1's facts are now **generated** (`ADR-2026-020`), so the counts cannot decay; added README-staleness and generated-handoff-facts to the beyond-the-build-order table, and §6.1–§6.2 for the refresher and its scheduled run. |
| v2.2 | 2026-10-13 | Closed decision 7: `ADR-2026-017` is `Superseded` by `ADR-2026-019` (which implemented it), and the hand-written `docs/decisions/index.md` no longer restates statuses — it points at the generated `docs/DECISIONS_INDEX.md`. |
