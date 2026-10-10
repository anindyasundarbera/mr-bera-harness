---
type: Decision Record
id: ADR-2026-005
date: 2026-10-10
title: The harness owns the agent loop and the LLM only proposes
status: Accepted
decision: Build the session harness so that it invokes the LLM, validates every proposal against schema and policy, and performs every execution itself; the model is never given execution authority.
covers: [MRB]
supersedes: []
---

# Context

The owner requires deterministic, validated agent behaviour, decisions persisted
across sessions, and exact bounded context so tokens are not spent on retrieval.

An LLM's semantic judgement cannot be made deterministic. A design that claims
otherwise is mislabelled. The question is therefore not "how do we make the model
deterministic" but "how do we build a deterministic system that may contain a
model".

Three ownership arrangements were considered:

1. the harness invokes the LLM and controls the loop;
2. the harness sits alongside an existing agent as a tool provider;
3. both modes.

# Decision

**The harness invokes the LLM and owns the loop.** The model returns
schema-validated *proposals* and executes nothing. The harness validates each
proposal against JSON Schema and policy, checks preconditions, then executes the
mutation with deterministic code and appends the result to an event log.

# Consequences

- **Every mutation has exactly one executor, and it is not the model.** This is
  what makes "every action validated" achievable: the validation surface becomes
  harness code, which is testable, rather than model reasoning, which is not.
- **Prevention over detection becomes available.** Because the harness exposes
  tools, a capability that must not be used simply is not offered — no
  `push_to_main` tool, no write tool before an approved work packet. Removing a
  capability is stronger than checking for its misuse.
- The advisory-only posture of ADR-2026-002 applies only to work done *outside*
  the harness. For work inside it, violations become impossible rather than loud.
- **Chain-of-thought is not validated.** It is unobservable and has no ground
  truth. Output and effect are validated; CoT is logged for debugging and never
  treated as evidence.
- Cost: adoption requires working through the harness. Model-agnostic by design —
  the proposal schema, not the provider, is the contract.
- Risk: a harness that owns the loop is more to build than a tool provider. The
  build order in `HARNESS_ARCHITECTURE.md` section 9 front-loads the deterministic
  layers, which are valuable regardless of which mode is used.

# Alternatives rejected

- **Tool-provider only.** Rejected as the primary mode: it constrains actions but
  does not own them, so "every action validated" cannot be guaranteed for
  anything the existing agent does outside the provider.
- **Custom protocol.** Rejected: the Agent Client Protocol already models
  propose/dispose and client-granted permission. Adopting its shape avoids
  inventing a permission model.
