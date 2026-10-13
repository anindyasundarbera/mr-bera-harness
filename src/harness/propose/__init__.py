"""Proposal schemas and effect gates.

Build-order step 4 of `HARNESS_ARCHITECTURE.md` §9. A model returns a proposal;
the harness decides whether to act on it. This package is the decision, not the
act: **nothing here executes anything.**

`validate_structure` answers *"is this well-formed?"*; `gate_proposal` answers
*"is this permitted?"*. §10.1 showed the provider enforces the first and cannot
enforce the second, so both are needed and neither is sufficient alone.
"""

from harness.propose.gate import (
    ALL_GATES,
    NOT_CHECKED,
    PERMITTED,
    REFUSED,
    RULE_BRANCH_FIRST,
    RULE_DECISION_NOT_MEMORY,
    RULE_NO_SECRET,
    RULE_ONE_CHANGE_PER_BRANCH,
    RULE_TEST_BEFORE_PUSH,
    RULE_WRITE_REQUIRES_PACKET,
    RULES_ENFORCED,
    Gate,
    Verdict,
    gate_proposal,
)
from harness.propose.schema import (
    INTENTS,
    PROPOSAL_SCHEMA,
    PROPOSAL_SCHEMA_VERSION,
    REQUIRED_BY_INTENT,
    SchemaUnavailableError,
    validate_structure,
)

__all__ = [
    "ALL_GATES",
    "INTENTS",
    "NOT_CHECKED",
    "PERMITTED",
    "PROPOSAL_SCHEMA",
    "PROPOSAL_SCHEMA_VERSION",
    "REFUSED",
    "REQUIRED_BY_INTENT",
    "RULES_ENFORCED",
    "RULE_BRANCH_FIRST",
    "RULE_DECISION_NOT_MEMORY",
    "RULE_NO_SECRET",
    "RULE_ONE_CHANGE_PER_BRANCH",
    "RULE_TEST_BEFORE_PUSH",
    "RULE_WRITE_REQUIRES_PACKET",
    "Gate",
    "SchemaUnavailableError",
    "Verdict",
    "gate_proposal",
    "validate_structure",
]
