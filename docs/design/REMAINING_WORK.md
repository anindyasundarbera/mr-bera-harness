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

`HARNESS_ARCHITECTURE.md` §9 lists six components. Three are implemented, merged
and on `main`.

| # | Component | State | Landed |
|---|---|---|---|
| 1 | Extraction + index | **Done** | PR #2 → `ADR-2026-006`, `CHG-2026-005` |
| 2 | Query API | **Done** | PR #4 → `ADR-2026-009`, `CHG-2026-008` |
| 3 | Prompt compiler | **In review** | PR #5 → `ADR-2026-010`, `CHG-2026-009` |
| 4 | Proposal schemas + effect gates | **Not started** | — |
| 5 | Session ledger | **Not started** | — |
| 6 | Instruction → prompt | **Not started** | — |

What each completed step provides:

| Step | Provides | Entry point |
|---|---|---|
| 1 | committed git → normalized model → derived Postgres index, proven rebuild-identical | `harness index build\|verify\|status` |
| 2 | lookups answered in SQL; element-wise scope matching | `harness query …` |
| 3 | work item + budget → deterministic prompt + content-bound fingerprint | `harness compile <id> --budget N` |

## 2. What is next: step 4 — proposal schemas + effect gates

> **Status: PARKED (owner instruction, 2026-10-13). Do not start this.**
>
> The owner asked for step 4 to be parked and to await an explicit request. An
> agent must not begin it, speculatively prepare it, or prepare a branch for it.
> This section exists so the next session knows the step is next **and** that
> starting it now would be a violation, not a judgement call.
>
> Everything already decided about it is recorded below, so the eventual session
> does not have to re-derive the contract — only to build against it.

The first step rated **Medium** risk, because it defines what a model may propose
and how a proposal is checked before anything executes. Everything so far is pure
code with no model in the loop; step 4 introduces the loop's contract.

The design constraints are already recorded:

- `ADR-2026-005` — the harness invokes the model and performs every execution;
  the model returns schema-validated proposals and executes nothing.
- `HARNESS_ARCHITECTURE.md` §10.1, validated experimentally on Ollama 0.34.0:
  native `format: <JSON Schema>` **enforces the schema at the sampling layer**,
  and **schema is enforced while semantics are not**. Every adversarial model
  returned a *valid* proposal that the attack had steered. The gates are
  therefore where the real checking lives — structure is the provider's job,
  meaning is the harness's.
- §7 — prefer the *impossible* class over the *loud* class: remove a capability
  rather than check for its misuse. No `push_to_main` tool; no write tool before
  an approved work packet.
- §1.1 — chain-of-thought is **not** validatable. Output and effect are.

A concrete design question to settle before coding: the proposal schema is the
contract, so it must be project-agnostic and versioned like `MODEL_VERSION` and
`INDEX_SCHEMA_VERSION` are. A schema change invalidates recorded proposals.

## 3. Then: step 5 — session ledger

`git notes` + Postgres. Records the prompt fingerprint (step 3), the proposal,
the verdict, and the effect. `git notes` survives a repository copy; Postgres
alone does not — which is why §10 lists the metadata store as an open decision
(option 4) even though `ADR-2026-001`'s entry-file pattern already carries the
decision record.

The fingerprint from step 3 is the join key: it is recorded *before* the model is
called, so a ledger entry can prove what was sent rather than assert it.

## 4. Last: step 6 — instruction → prompt

`No` under "Deterministic?", **High** risk, and deliberately last. §9 says the
design must not depend on it:

> a human who writes the task ID directly bypasses step 6 entirely and loses
> nothing.

Intent classification is fuzzy; §8 records it as not achievable as stated. Do not
let any other step depend on it.

## 5. Open decisions — do not guess these

Each is `DecisionRequired`. None may be supplied by a plausible default.

| # | Decision | Why it is blocking | Where recorded |
|---|---|---|---|
| 1 | **Budget unit** — is a model tokenizer adopted? | the compiler uses an exact word count today; adopting a tokenizer changes what every recorded budget means and makes old budgets incomparable | `ADR-2026-010` |
| 2 | **PostgreSQL version** for the index | no authoritative document fixes one, so no version is asserted in code or in CI beyond the `postgres:16` image the test job uses as a fixture | `ADR-2026-006` |
| 3 | **Entry location** — `docs/DECISIONS_INDEX.md` says entries live in `knowledge/decisions/`, but `harness.toml` sets `decisions = "docs/decisions"` | the generated header contradicts the configuration; entries were placed per the config and the header text left unchanged | open |
| 4 | **`workflow` scope for agent sessions** | a token without it cannot push `.github/workflows/**`; SSH works but is a workaround | open |
| 5 | **Postgres locality / index lifecycle** | §10 options 1–2; step 1 chose rebuild-on-demand implicitly by having no long-running service | `HARNESS_ARCHITECTURE.md` §10 |
| 6 | **`harness ci` has no consumer pipeline** | invoked in a repository other than the harness it runs the *harness's own* stages — wheel build, `mypy src`, `pytest tests/` — and fails with a misleading message. See §6.1 | open |

### 5.1 A consumer test found what the unit tests could not

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

## 6. Housekeeping and environment traps

### 6.1 `harness ci` is not project-agnostic

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

### 6.2 Traps already paid for
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
- **"Works locally" is not evidence.** CI caught two defects a green local run
  could not: a missing git identity in fixtures, and a coverage floor enforced
  against code CI never ran.

## 7. How to verify the current state

```bash
cd <repo>
pip install -e ".[dev,postgres]"
harness doctor                                  # clean?
harness guards                                  # refuses a protected branch, by design
python -m pytest -q                             # without a database
MRB_TEST_DSN=... python -m pytest -q            # with one
harness ci --workflow .github/workflows/ci.yml  # rehearsal + parity
```

Expected on `main` after step 3 merges: `harness doctor` clean, `harness guards`
refuses `main`, tests green, coverage above the 80% floor, `harness ci` passed.

## 8. Change history

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-10-13 | Recorded the build-order state after steps 1–3, the step 4–6 contract, five open decisions and the environment traps. |
| v1.1 | 2026-10-13 | Added decision 6 (`harness ci` is not project-agnostic) and §5.1, the fresh-consumer test result that found it. |
| v1.2 | 2026-10-13 | Marked step 4 **parked** by owner instruction: do not start it without an explicit request. Steps 4–6 unchanged otherwise. |
