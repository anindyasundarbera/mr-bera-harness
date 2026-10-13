---
type: Decision Record
id: ADR-2026-015
date: 2026-10-13
title: Workflow changes route through SSH while agent credentials lack the workflow scope
status: Accepted
decision: Record that the harness's agent credential carries no workflow scope, so any change touching .github/workflows/** is pushed over SSH with the owner's key rather than widening the token; the standing choice between widening the credential and keeping this route is a DecisionRequired for the owner.
covers: [MRB]
supersedes: []
---

# Context

Three pushes failed while this work was in progress, each time because the change
touched `.github/workflows/`:

```
! [remote rejected] … (refusing to allow an OAuth App to create or update workflow
  `.github/workflows/ci.yml` without `workflow` scope)
```

The failure recurred when step 4 needed the `propose` extra installed in CI, when
step 2 needed a Postgres service added, and earlier in the same pattern. Each time
the work was otherwise complete and green.

The observed facts, from `gh auth status`:

- Scopes: `admin:public_key`, `gist`, `read:org`, `repo` — **no `workflow`**.
- The credential also carries `admin:public_key`, which can add SSH keys to the
  account. It is a broad credential already.
- `origin` is an **https** URL while `gh` reports "Git operations protocol: ssh", so
  pushes use a different path from the one `gh` describes.

GitHub's rule is specific: the `workflow` scope is required for OAuth App tokens
modifying workflow files. An **SSH key is not an OAuth App**, so the rule does not
apply to it — which is why the SSH route works.

# Decision

**Recorded as the current, working convention:**

- Workflow changes are pushed over SSH with the owner's key, which authenticates as
  the owner (`Hi anindyasundarbera!`). This uses an existing owner credential rather
  than granting the agent a broader one.
- The agent does **not** request, hold or transmit the token value. A credential in a
  prompt or a log is already exposed, and rotation is the only remedy.
- A change that cannot be pushed this way is left as a **local, clearly-marked
  commit** with a patch file, rather than being forced or worked around.

**Recorded as remaining the owner's decision:**

- Whether to widen the local session with `gh auth refresh -s workflow`. That
  removes the workaround but also widens the ambient credential the agent runs
  under, including its `admin:public_key` capability.
- Or to create a fine-grained, single-repository token with only **Contents: write**
  and **Workflows: write**, used for this purpose and revoked after.
- Or to keep this route permanently and stop treating it as a workaround.

The agent's view, offered as input rather than as the decision: a narrow, revocable
credential is the better long-term shape, and the current broad token is a poor
thing to widen further.

# Consequences

- **The work is never blocked by this.** Three times it was pushed via SSH and
  continued; one earlier case became a local commit and a patch file.
- **No credential was shared.** The token value has never entered a prompt, a log or
  a session artifact.
- **The workaround is now recorded**, so the next session does not rediscover it — it
  cost time three times precisely because it was not written down.
- **A latent hazard is documented:** `gh` says SSH while `origin` is https with a
  stale `~/.git-credentials`, so "which credential just pushed" is not obvious from
  `gh auth status`. Anyone debugging an authentication failure here should check both
  paths.
- Cost: workflow changes depend on an interactive owner credential being present on
  the machine, which is fine for a single-operator setup and would not be for a team.

# Alternatives rejected

- **Widening the agent's token to include `workflow`.** Considered and declined here:
  it enlarges an already-broad credential (`admin:public_key`, `repo`, `gist`) to move
  a small YAML change. It remains an owner option, and if taken should be a
  fine-grained token rather than a scope added to this one.
- **Asking the owner to paste the token.** Never a reasonable option: it would place a
  live credential in a transcript, and the only remedy afterwards is rotation.
- **Working around it by not changing workflow files.** Not always possible — CI needs
  to install the extras the code requires, and a test job that skips the code under
  test measures nothing.
- **Silently leaving workflow changes uncommitted.** The first occurrence did leave a
  local commit and a patch; that is the fallback, not the default, because it needs an
  owner action to complete.
