"""The proposal contract: what a model may propose, and nothing else.

A model never executes anything (`ADR-2026-005`). It returns a **proposal**, and
the harness decides whether to act on it. This module is the first half of that
split: the schema a proposal must satisfy.

Two facts from `HARNESS_ARCHITECTURE.md` shape it:

* §10.1, validated experimentally on Ollama 0.34.0: native
  `format: <JSON Schema>` **enforces the schema at the sampling layer**. Under an
  adversarial prompt every model stayed inside the schema.
* The same experiment showed **schema is enforced while semantics are not** — each
  adversarial model returned a *valid* proposal the attack had steered. So this
  schema is necessary and **not sufficient**: meaning is checked by the gates.

Because it is the contract, it is **versioned**. A schema change invalidates a
recorded proposal, and a proposal that does not state its version cannot be
checked against the right one.

The `intent` enum is derived from the enumerated rules in §7.1, not invented
here: each value corresponds to a rule the architecture already names.
"""

from __future__ import annotations

from typing import Any

#: Bumped whenever the schema below changes. A proposal records the version it was
#: made against, so a changed contract cannot silently reinterpret an old one.
PROPOSAL_SCHEMA_VERSION = 1

#: The proposable intents, one per rule enumerated in `HARNESS_ARCHITECTURE.md`
#: §7.1. Deliberately small: an intent exists only if a rule names the behaviour.
INTENTS = (
    # `switch to a new branch for new development` — branch creation is the first
    # harness action, so it is the only intent permitted on a protected branch.
    "create_branch",
    # `do not write code unless explicitly instructed` — gated on an approved
    # work packet; refused without one.
    "write_file",
    # `test before push` — permitted only once the test effect-check has passed.
    "push",
    # `write a decision, not a memory` — must produce an entry file.
    "record_decision",
    # The propose/dispose split itself: the model may ask for human permission,
    # which is a request, not a mutation.
    "request_permission",
)

#: The schema, as a plain dict so it can be handed to a provider unchanged
#: (``format`` for Ollama) and used locally by the same validator.
PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/anindyasundarbera/mr-bera-harness/proposal-v1.json",
    "title": "Harness proposal",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "work_id", "intent", "summary"],
    "properties": {
        "schema_version": {
            "const": PROPOSAL_SCHEMA_VERSION,
            "description": "The contract this proposal was made against.",
        },
        "work_id": {
            "type": "string",
            "minLength": 1,
            "description": "The work item the proposal concerns.",
        },
        "intent": {
            "enum": list(INTENTS),
            "description": "One of the behaviours a rule in architecture 7.1 names.",
        },
        "summary": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "A one-line statement of what is proposed, for a human.",
        },
        "target_path": {
            "type": "string",
            "description": "A repository-relative path. Required for the intents that name one.",
        },
        "branch": {
            "type": "string",
            "description": "Branch name, for `create_branch` and `push`.",
        },
        "content_digest": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
            "description": "SHA-256 of the proposed content, so the effect is bound to bytes.",
        },
        "work_packet": {
            "type": "string",
            "description": "The approved work packet authorising a write. Required to write.",
        },
        "entry_id": {
            "type": "string",
            "description": "Entry identifier a decision record will carry.",
        },
        "test_effect_passed": {
            "type": "boolean",
            "description": "Whether the in-session test effect-check has passed.",
        },
        "requested_action": {
            "type": "string",
            "description": "What permission is being requested, for `request_permission`.",
        },
    },
    # Conditional requirements keep the schema honest about what an intent needs,
    # so an incomplete proposal cannot be structurally valid.
    "allOf": [
        {
            "if": {"properties": {"intent": {"const": "write_file"}}, "required": ["intent"]},
            "then": {"required": ["target_path", "work_packet", "content_digest"]},
        },
        {
            "if": {"properties": {"intent": {"const": "create_branch"}}, "required": ["intent"]},
            "then": {"required": ["branch"]},
        },
        {
            "if": {"properties": {"intent": {"const": "push"}}, "required": ["intent"]},
            "then": {"required": ["branch"]},
        },
        {
            "if": {"properties": {"intent": {"const": "record_decision"}}, "required": ["intent"]},
            "then": {"required": ["entry_id"]},
        },
        {
            "if": {
                "properties": {"intent": {"const": "request_permission"}},
                "required": ["intent"],
            },
            "then": {"required": ["requested_action"]},
        },
    ],
}

#: Which fields each intent requires, kept alongside the schema so the gates and
#: the documentation can both read one source rather than restating it.
REQUIRED_BY_INTENT: dict[str, tuple[str, ...]] = {
    "create_branch": ("branch",),
    "write_file": ("target_path", "work_packet", "content_digest"),
    "push": ("branch",),
    "record_decision": ("entry_id",),
    "request_permission": ("requested_action",),
}


class SchemaUnavailableError(Exception):
    """Raised when no JSON Schema validator is installed.

    The architecture specifies validation *against JSON Schema*. Hand-rolling a
    subset would accept some invalid documents, and refusing silently would be
    worse, so absence is a loud failure with a fix in the message.
    """


def validator() -> Any:
    """Return a JSON Schema validator for the proposal schema.

    `jsonschema` is the standard implementation of the format the architecture
    names. Reimplementing a validator would be a second, subtly different
    definition of validity — the drift this project exists to avoid.
    """
    try:
        import jsonschema  # noqa: PLC0415 - optional dependency, loaded on demand
    except ImportError as exc:  # pragma: no cover - depends on the install extras
        raise SchemaUnavailableError(
            "no JSON Schema validator installed. Proposals are validated against "
            "JSON Schema, so install the extra: pip install -e '.[propose]'"
        ) from exc
    return jsonschema.Draft202012Validator(PROPOSAL_SCHEMA)


def validate_structure(proposal: object) -> list[str]:
    """Structural validation only. Returns human-readable problems.

    This answers *"is this a well-formed proposal?"* and nothing else. It says
    nothing about whether the proposal is permitted — that is the gate's job, and
    conflating the two is exactly the error §10.1 warns about.
    """
    problems: list[str] = []
    for error in sorted(validator().iter_errors(proposal), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in error.path) or "(root)"
        problems.append(f"{location}: {error.message}")
    return problems
