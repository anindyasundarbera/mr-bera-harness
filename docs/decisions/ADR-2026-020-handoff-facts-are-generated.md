---
type: Decision Record
id: ADR-2026-020
date: 2026-10-13
title: The handoff's mechanical facts are generated, and its narrative is not
status: Accepted
decision: Split the live handoff into a hand-written narrative and a generated fact region delimited by markers, refreshed by tools/refresh_handoff.py from the harness's own derivations, so the counts cannot decay while the judgement stays a human edit.
covers: [MRB]
supersedes: []
---

# Context

`docs/design/REMAINING_WORK.md` is the document every new session is told to read
first (`AGENTS.md` §2, and the handoff brief itself). It is a **handoff**, which means
its whole value is being true, and it has already been false once: the v2.0 refresh
found it describing steps 1–3 as the state and steps 4–6 as "not started" when all six
were merged, and recorded that *"a handoff that is wrong is worse than none, because it
is trusted"*.

That was fixed by rewriting the document. But the specific facts that were wrong are
the kind a machine knows exactly — the revision, the test count, the entry and concept
counts — and they had been refreshed **by hand**, in prose, in a table. Hand-refreshed
facts decay the moment the next change lands, and this repository has already paid for
that twice in one file:

- `CHG-2026-016` — a generated header **hardcoded** a source path it should have read
  from configuration.
- `CHG-2026-020` — the README still asserted a gap was open, four hours after the merge
  that closed it, because the change updated `PURPOSE.md` and not the README.

The requirement is the one `PURPOSE.md` states for the whole project: an answer a
programme can read and a test can check, rather than prose that drifts.

# Decision

1. **The handoff is split in two, by markers.** `<!-- harness:handoff-facts:start -->`
   and `<!-- harness:handoff-facts:end -->` delimit a region that is **generated**.
   Everything outside them is hand-written and is never touched.

2. **`tools/refresh_handoff.py` owns that region.** It derives every value from the
   repository through the harness's own library — the OKF `Bundle` for the concept
   count, the entries `validate_all` for the entry counts, the provenance `check` for
   the declaration count, the resolved `Config` for the commit vocabulary. It does
   **not** re-implement any of them: a second implementation would be a second
   definition of "the entry count", and the two would drift — the failure this decision
   exists to prevent, reintroduced in the fix.

3. **The region holds only facts that are functions of the committed content.** Two
   categories are excluded, and the first exclusion was found by building the thing
   rather than by reasoning ahead:

   - **The revision and the dirty flag.** A committed file cannot contain its own
     commit's hash. A region stating `Revision: <HEAD>` is therefore **stale the instant
     it is committed**, `--check` could never return `0`, and a scheduled job would
     rewrite the same lines forever. This was observed: the first implementation
     rendered the revision, and the region could not settle. A handoff that names a
     revision must write it by hand, which is honest — it is then visibly a claim a
     person made rather than one that appears machine-derived.
   - **The test pass and skip counts.** They describe the *environment*, not the
     repository: the same commit reports one pair without a database and a different
     pair with one. Generating them would make `--check` differ between a laptop and CI,
     which is the class of defect this repository has already paid for twice — a
     coverage floor measured differently with and without `MRB_TEST_DSN`. Test results
     belong in the changelog entry, with their provenance.

   The rule stated once: **a fact about the checkout, or about the machine running the
   script, is not a fact about the repository.**

4. **The narrative stays a human edit.** The script writes a table of derived values
   and nothing else. What was built, what is blocked, what the next session should do
   is a judgement, and a script that generated it would be **inventing a handoff** —
   the same failure as inferring a code-to-decision link (`ADR-2026-017`).

5. **The markers are required, and their absence is a refusal.** A handoff without them
   exits `2` rather than doing nothing quietly: a silent no-op would report success
   while refreshing nothing, which is worse than refusing because the caller would
   believe it had succeeded.

6. **Three-valued exit codes**, matching the harness's contract: `0` current or
   refreshed, `1` `--check` found the region stale, `2` usage or unparseable handoff.
   The `1` is what a scheduled job acts on without mutating anything.

7. **The schedule is a trigger, not an authority.** The refresh runs as a scheduled
   agent session on the Local Agent Host, not in CI: CI validates a candidate, whereas
   this repairs a document, and the two are different questions — the same distinction
   `ADR-2026-008` draws for the session guards. The session works on a branch and opens
   a draft PR; it cannot merge, and a human reviews it like any other PR.

# Consequences

- **The counts cannot decay silently.** `--check` exits `1` when the region differs from
  the repository, so a scheduled run can refresh it and a reader can ask whether the
  handoff is current.
- **`--check` can actually settle**, which is the property the first design lacked. The
  region is committed with no fact that changes at commit time, verified on a real
  commit: `--check` returns `0` on the committed tree, not only on a working copy.
- **Proven end to end, not asserted.** Tampering with a value in the real handoff made
  `--check` exit `1`; running the refresher restored it and `--check` returned `0`.
- **The blast radius is one marked region.** The splice is required to leave every byte
  outside the markers unchanged, and a test asserts it — including that the prose above
  and below survives.
- **The exclusion rule is pinned by a test**, not only by prose: the `Facts` dataclass is
  asserted to carry no revision, branch, dirty flag or test count, so re-adding one
  fails the suite with the reason attached.
- Cost: the handoff now has syntax a reader must not break. Deleting a marker is caught
  (exit `2`), and a test asserts the markers are present, so that cost is bounded.
- Cost: `tools/` is a new top-level directory. It is the harness's default for the
  `paths.tools` configuration key, though this repository's `harness.toml` points that
  key at `src`; nothing in the harness reads either, so the risk is low.
- **Stated limit:** the script proves the region matches the repository's derivations.
  It does **not** prove the narrative above it is true — the v1.0 staleness was prose,
  and no marker can catch prose. The scheduled session edits the narrative; the script
  is what makes the facts under it trustworthy.

# Alternatives rejected

- **Generate the whole handoff.** It would have to invent the narrative — what was
  built, what is risky, what is next — which is a judgement presented as a derivation.
  That is the failure mode this repository exists to prevent.
- **Include the revision, so the handoff says what it was written against.** Tried in
  the first implementation and rejected by observation: the region then cannot be
  current after a commit, so the check could never pass and the job would churn. The
  revision is hand-written instead, where its impermanence is visible.
- **Include the test counts.** Rejected for the same shape of reason: they are a property
  of the environment, so the check would differ between a laptop and CI.
- **A test that asserts the handoff's facts.** It would run the suite from inside the
  suite (recursion), and it would still not reach prose.
- **Leave it by hand, but be careful.** It has already been wrong once, and "be careful"
  is not a mechanism.
- **Write the facts into a separate status file and never into the handoff.** Then the
  handoff would still carry hand-copied numbers — the second copy is the defect, not the
  fix. The generated region is *in* the document precisely so the reader of the narrative
  sees true numbers without a second document to reconcile.
