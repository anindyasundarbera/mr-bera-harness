---
type: Decision Record
id: ADR-2026-004
date: 2026-10-10
title: Guards activate at the start of every agent session
status: Accepted
decision: Require every coding-agent session to run tools/activate_guards.py before doing work, and refuse the session when it finds a protected branch, a tracked secret, conflict markers or failing invariants.
covers: [MRB]
supersedes: []
---

# Context

Branch rules that live only in prose are followed inconsistently. The framework
already required fixed verification, review and approval, yet nothing made an
agent *start* from a valid state. A session could begin on `main` with a tracked
secret and never notice.

# Decision

`tools/activate_guards.py` runs first in every session, wired into `AGENTS.md`
so an agent discovers it before anything else. It checks six things and exits
non-zero on any failure:

1. the branch is an allowed feature branch, never the default;
2. no unresolved merge conflicts;
3. no forbidden path tracked (`git ls-files` — the check `.gitignore` cannot do);
4. nothing forbidden staged;
5. no conflict markers in tracked sources;
6. routing, entry and resolver invariants all pass.

# Consequences

- The session begins from a **verified state**, not an assumed one.
- Checks 3 and 4 exist because `.gitignore` governs untracked files only:
  an already-tracked secret needs `git rm --cached` and would otherwise pass
  every ignore-rule check while remaining committed.
- The guard is **advisory at the server boundary** (ADR-2026-002) and says so in
  its own output. It makes the wrong action loud and immediate; it does not make
  it impossible. `pre-push --no-verify` still bypasses the hook.
- Cost: a failing guard blocks the session until the finding is resolved. That
  is the intended behaviour.
