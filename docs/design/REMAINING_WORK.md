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

## 6. Housekeeping and environment traps

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
