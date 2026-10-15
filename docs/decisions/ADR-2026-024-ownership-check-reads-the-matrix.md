---
type: Decision Record
id: ADR-2026-024
date: 2026-10-15
title: The routing ownership check reads the contract's matrix, and a disclaimer is not a claim
status: Accepted
decision: Redefine routing check 6 to read the state-ownership matrix from the routing contract rather than infer ownership from frontmatter, to treat do_not_use_for as the disclaimer the contract defines it to be, and to accept either spelling of the field so the check cannot pass vacuously.
covers: [MRB]
supersedes: []
---

# Context

Routing check 6 was documented as *"no `do_not_use_for` state-ownership key is claimed by two
modules"*, and implemented by grouping every concept's `do_not_use_for` list by module and
reporting any key listed by two modules.

Three things were wrong with that, and all three were invisible while **M06 was the only
module**.

**1. It inverted the field's meaning.** `DOCUMENT_ROUTING.md` §4 states the semantics in one
sentence:

> an M06 document listing `do-not-use-for: [commerce-truth]` means "this document must **not**
> be used to define price or stock — that is M03's"

So a listing is a **disclaimer** pointing at the owner. The check counted it as a **claim**.
The resolver agrees with the prose — its only use of the field is **exclusion**
(*"excluded when its `do_not_use_for` names a state the caller intends to define"*), which is
coherent only under the disclaimer reading: under the claim reading it would exclude a
document *because it owns the state*.

**2. The harness's own test encoded the inversion.** `test_two_modules_claiming_one_key_detected`
asserted that two modules listing one key **is** a violation — so the defect was pinned in
place by a passing test.

**3. It read only one spelling, and so could go vacuous.** The contract writes the field
`do-not-use-for`; OKF concepts in practice use `do_not_use_for`. Check 6 read the underscored
form only, while the resolver accepted both. Measured on a spec-conformant document set:
**check 6 saw 0 of 90 keys** — `routing invariants: 0 violation(s)` while the guard had not
run at all. A guard that reports a clean result without checking is worse than one that is
wrong, because it cannot be distinguished from a pass.

**Why it surfaced now.** Every one of these is harmless for a single-module bundle: with one
module, no key can be listed by two of them, and the one spelling in use is the one the code
reads. Authoring M05, M07 and M03 for `FRAMEWORK-007`'s routing rows supplied the **first
second module**, and 13 false collisions appeared. The check could never have passed for a
repository with more than one module, because every module correctly disclaims the same shared
keys.

# Decision

1. **Ownership is read from the contract's matrix, never inferred.** A new
   `state_ownership(path)` parses the `| \`key\` | MRB-Mnn | meaning |` rows of the routing
   contract, which §4 declares as the authority (*"Each key has **exactly one** owning
   module"*). The file is located through a new `paths.routing` config key (default
   `docs/DOCUMENT_ROUTING.md`), so no filename is hardcoded — the defect this repository has
   fixed five times.

2. **The check now verifies two things a disclaimer must satisfy**, instead of counting
   listings:
   - the key it names is **a real key** in the matrix — a disclaimer that warns nobody is a
     defect;
   - the disclaiming module **is not the owner** of that key — *"do not use me to define what
     I own"* is incoherent, and a reader cannot tell which statement binds.

3. **Both spellings are read**, matching the resolver, so the check cannot silently skip the
   documents it is meant to check.

4. **The old semantics are removed, not kept beside the new.** `owners_key()` is deleted —
   it existed only to attribute a claim — and the test that asserted the inversion is rewritten
   to assert the correct behaviour, with its docstring saying *why* the assertion is the
   opposite of what it was.

# Consequences

- **`mr_bera`'s bundle passes for the first time.** Measured: 45 concepts, **0 routing
  violations**, where the old check reported **13**. The 13 were not defects in the documents;
  they were the check misreading correct disclaimers.
- **The check is live, not vacuous.** Verified by injection: a concept under `MRB-M03`
  declaring `do_not_use_for: [commerce-truth]` — a key M03 owns — is now reported.
- **`FRAMEWORK-007`'s replication gate is unblocked** for the part that depended on this: rows
  7 and 9 resolve, and row 10's cross-module load is correct. The routing test can now be
  completed to 10/10.
- **A contract change, not only a code change.** The check's documented meaning in
  `DOCUMENT_ROUTING.md` §5 changes; `mr_bera`'s copy of that document must be updated in the
  same breath, or the two disagree.
- Cost: the check now depends on the contract being present and parseable. When it is absent,
  `state_ownership()` returns empty and the per-key checks are **skipped** — the same silent
  degradation this decision exists to remove, in a new place. The mitigation is that an empty
  matrix is detectable, and a project without a routing contract has no ownership rules to
  enforce; but it is a real cost and is not hidden.
- Cost: `validate()` gains a parameter, so every caller must pass it or lose the check. Only
  `validate_routing()` calls it in-repo, and both test call sites go through that.

# Alternatives rejected

- **Count `owner_module` as the claimant instead of the module.** Closer, but still infers
  ownership from the documents being checked — so a bundle could declare two owners and the
  check would agree with both. The matrix is the authority; read it.
- **Keep the claim reading and instead forbid modules from disclaiming shared keys.** That
  deletes §4's usage rule, which exists precisely so an agent is warned *before* it writes a
  price. The rule is load-bearing.
- **Fix the spelling by changing every concept to the hyphenated form.** That would turn the
  check green while making it check nothing — measured: 0 of 90 keys seen. A green result that
  is vacuous is the failure mode here, not the fix.
- **Leave `owners_key()` in place for compatibility.** It has no callers and is not exported.
  Keeping a function whose stated purpose is the inference just removed would invite its
  return.
- **Report the defect and change nothing.** It would leave the guard blind, the test asserting
  the wrong thing, and `FRAMEWORK-007` permanently inert — and the owner has directed that this
  be closed.
