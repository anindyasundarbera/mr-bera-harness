"""MrBera session harness — a deterministic context layer for coding agents.

The harness is importable and project-agnostic. A consuming repository supplies a
`harness.toml`; the harness then reads that repository's documents, frontmatter
and registries without knowing anything about them in advance.

Design principle, from `docs/HARNESS_ARCHITECTURE.md`:

    The LLM proposes; the harness disposes.

The model returns schema-validated proposals and executes nothing. Deterministic
code validates each proposal and performs every mutation, so the validation
surface is testable code rather than model reasoning.
"""

from __future__ import annotations

from harness.config import Config, load_config
from harness.routing import parent_chain

__version__ = "0.2.0"

__all__ = ["Config", "load_config", "parent_chain", "__version__"]
