---
id: OKF-MOD-SYS-001
module: MRB-LRF
class: framework
canonical: true
covers: [MRB]
depends-on: [AI_RND_FRAMEWORK.md, DOCUMENT_ROUTING.md, DOCUMENTATION_STRUCTURE.md, PROJECT_DECOMPOSITION.md]
do-not-use-for: []
read-budget: must-read
---

# MrBera OKF Module System

> ID: OKF-MOD-SYS-001
>
> Status: **Proposed framework artifact v0.1** — introduced alongside `FRAMEWORK_CHANGE_FRM_2026_002.md`; awaiting owner ratification.
>
> Authority: this document describes **how the module system is built and run**. It creates no architecture, holds no decision status, and overrides no registry. `docs/` remains the single source of truth; the bundle is a routing layer over it.
>
> Format basis: **Open Knowledge Format (OKF) v0.2** — `GoogleCloudPlatform/open-knowledge-format`, `SPEC.md`.

---

## 1. What this is

A **directory-based module system** in which each MRB module is an OKF bundle subtree, and small Python executables resolve the exact context an agent needs before it starts work.

Three parts:

| Part | Location | Role |
|---|---|---|
| **Bundle** | `knowledge/` | OKF v0.2 concepts describing each module: architecture, interfaces, success criteria, unknowns |
| **Tools** | `src/harness/` | A read-only Python package with one entry point, `harness` |
| **Attestation** | `knowledge/references/attesters/` | Deterministic (no-LLM) code that checks a tool ran the sanctioned way |

The bundle **points at** `docs/`; it never duplicates it. One canonical copy per artifact, per `DOCUMENTATION_STRUCTURE.md` §2 rule 1.

---

## 2. Why it reduces hallucination

An LLM fabricates when it must emit a token with no grounded source. In a development context there are five triggers; each has a countermeasure here:

| Trigger | Countermeasure | Where |
|---|---|---|
| A value is needed but absent from context | Bounded, mechanically selected context slice | `okf_context.py` |
| A value is genuinely undecided | `Unknown` concepts that **halt** with a named blocker | `knowledge/**/unknowns/` |
| The decision state is ambiguous | Frontmatter carries no status; registries are authoritative | `DOCUMENT_ROUTING.md` §2.2 |
| The stopping point is unknown | Non-zero exit + explicit stop list | `okf_context.py` exit 3 |
| The done-state is unknown | Success criteria with a mandatory "not yet assertible" section | `knowledge/**/success-criteria/` |

The critical property: **`okf_context.py` exits 3 when a stop condition applies.** An agent cannot silently proceed past an undecided value; the tool refuses.

---

## 3. Bundle layout

```
knowledge/
  index.md                  # bundle root; carries okf_version: "0.2"
  log.md                    # chronological change history
  governance/
    registries/             # pointers to the four authoritative registries
  modules/
    M06-local-ai/
      index.md
      architecture.md       # covers: [MRB-M06]
      interfaces.md
      success-criteria/
        assertions.md
        not-yet-assertible.md
      unknowns/             # type: Unknown — stop conditions
      providers/
      orchestration/
      computations/         # type: Attested Computation
  references/
    skills/                 # executor instructions
    attesters/              # deterministic verification code
```

Reserved filenames `index.md` and `log.md` have defined meaning at every level (OKF SPEC §3.1) and are never concept documents.

---

## 4. The two extensions over OKF

OKF v0.2 is a general knowledge format. Two **producer-defined** concepts are added for module routing. Both are legal under SPEC §4.1 ("producers MAY include any additional keys").

### 4.1 `Unknown` — a stop condition as a first-class concept

```yaml
type: Unknown
state: BlockedOwner          # mirrors GAP_REGISTER taxonomy
blocker: CONTROL-STORE-01    # the decision or evidence that must land
blocks: [MRB-M06-S14-C02]    # decomposition IDs this halts
if_you_guess: <consequence of proceeding anyway>
must_not_do: [<prohibited action>]
```

An `Unknown` is never loaded as content — the resolver surfaces it only as a stop condition.

### 4.2 `Attested Computation` — the sanctioned way to produce a value

Used natively per SPEC §10, with `runtime: python`. Each computation declares its parameters, its executor (a Skill), and its attester (deterministic code). An agent may supply **values for declared parameters only**; it must never author or edit the computation itself (SPEC §10.3).

This is what makes "did the sanctioned thing run?" a mechanical comparison rather than a judgement call.

---

## 5. Running the tools

```bash
# Resolve the context pack for a work item
harness context MRB-M06-S14-C02

# Declare the states you intend to define (activates do_not_use_for exclusion)
harness context MRB-M06-S02-C01 --defining commerce-truth

# Machine-readable
harness context MRB-M06-S14-C02 --json

# OKF v0.2 conformance over the bundle
harness conform
```

### 5.1 Exit codes

| Code | Meaning | Agent action |
|---|---|---|
| `0` | Context resolved, no stop condition | Proceed with the listed concepts |
| `2` | Usage error or malformed identifier | Fix the invocation |
| `3` | **A stop condition applies** | **Stop.** Record the specific blocker. Do not proceed. |
| `4` | **No concept covers this chain** | **Stop.** Record `BlockedDependency`. Do not invent a concept. |

Codes `3` and `4` both halt work but mean different things: `3` names a specific blocker, `4` says the chain has no specification at all. `3` takes precedence when both apply.

Exit `0` with an empty `load` list is **not possible** — that case returns `4`. This is deliberate: treating "nothing to load" as success would let an agent proceed with no grounding at all.

### 5.2 Attesting a run

```bash
python3 knowledge/references/attesters/deterministic_output.py receipt.json
```

The attester checks that the sanctioned tool ran, the exit code is recognised, the output parses, and the receipt is internally consistent — specifically that an agent has not claimed `exit_code: 0` while the output still carries stop conditions.

---

## 6. Routing rules

1. Walk the work item's parent chain: `MRB-M06-S07-C03-W01-A02` → … → `MRB-M06`.
2. Select concepts whose `covers` intersects that chain.
3. Order by `read_budget`: `must-read` before `reference-only`.
4. Exclude any concept whose `do_not_use_for` names a state you intend to define.
5. Read `Unknown` concepts that block the chain as **stop conditions**, not as content.

Full contract and the ownership-key matrix: `DOCUMENT_ROUTING.md`.

---

## 7. Verified behaviour

Recorded from the prototype run (2026-10-10, M06 only):

| Check | Result |
|---|---|
| OKF v0.2 conformance over the bundle | **0 problems**, 23 concepts |
| `MRB-M06-S14-C02` (config store) | exit **3**, 1 stop: `CONTROL-STORE-01` |
| `MRB-M06-S07-C03-W01-A02` (design pipeline) | exit **3**, stops incl. `DESIGN-RUBRIC-01` |
| `MRB-M06-S03-C01` (provider registry) | exit **3**, stops incl. `CONTROL-SECRET-01` |
| `MRB-M03-S02-C01` (**cross-module**) | exit **4**, **0 M06 concepts loaded** |
| `MRB-M04-S05-C01` (**cross-module**) | exit **4**, **0 M06 concepts loaded** |
| `--defining commerce-truth` | 8 concepts excluded with reason |
| Valid receipt | attester **PASS** |
| Forged receipt (`exit 0` + stops) | attester **FAIL** — contradiction caught |

The cross-module rows are the decisive ones: an M03 task loads nothing from M06.

### 7.1 Test suite

`tests/` holds **171 tests**, executable in CI and locally:

```bash
python3 -m pytest tests/ -q --cov=tools
```

| File | Covers |
|---|---|
| `test_okf_reader.py` | Frontmatter parsing, trust tiers, staleness, path resolution, links, conformance |
| `test_okf_context.py` | Parent-chain grammar, selection, exclusion, stop conditions, exit codes, and every row of the §8 routing test |
| `test_attester.py` | Pass path, every failure class, adversarial receipts, real end-to-end pipeline |
| `test_validate_routing.py` | Each routing check with passing *and* failing fixtures |

Coverage is measured with `patch = subprocess`, so the CLI contract tests count: **90%** over the three tools.

### 7.2 Continuous integration

`.github/workflows/ci.yml` runs four jobs on every push and pull request:

| Job | What it enforces |
|---|---|
| `lint` | `ruff check` + `ruff format --check` |
| `typecheck` | `mypy --strict` over `tools/` |
| `test` | pytest with coverage, matrix **3.10 / 3.11 / 3.12 / 3.13** |
| `governance` | OKF conformance, routing invariants, and the resolver exit-code contract |

The governance job is the one that matters for this system: it fails the build if the bundle stops conforming, if a routing invariant breaks, or if the resolver's stop-contract regresses.

---

## 8. Governance position

- The bundle is a **routing layer**, not an authority. It carries no decision status, value or threshold.
- `docs/` remains canonical. `DOCUMENTATION_STRUCTURE.md` §9 still applies: no target-path copies.
- `GAP_REGISTER.md` remains the sole gap authority; `Unknown` concepts are a **derived, module-scoped view**.
- Extending the bundle for other modules is **gated** on owner ratification of `FRM-2026-002`.

---

## 9. Limitations (stated plainly)

| Limitation | Detail |
|---|---|
| **Routing test not run against a real backlog** | The tasks above are representative, not the live backlog. Precision/recall is **unmeasured**. |
| **M06 only** | M01–M05, M07–M11 have no bundle subtree yet. |
| **`do_not_use_for` uniqueness is not machine-checked by the tools** | It is asserted in `DOCUMENT_ROUTING.md` §4 but only manually verified so far. |
| **Attester is a consistency check, not a correctness proof** | It verifies the receipt shape, not that the resolver's selection is *right*. |
| **No receipt is persisted** | Per SPEC §10, receipts are runtime artifacts and are deliberately not stored in the bundle. |
| **PyYAML required** | `pip install pyyaml`. |

---

## 10. Change history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-10-10 | Initial system; M06 vertical slice. OKF v0.2 bundle + two Python tools + deterministic attester. No gate executed. |
