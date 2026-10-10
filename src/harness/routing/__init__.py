"""Work-identifier routing.

The routing layer turns an identifier into the set of documents that bind it.
Its grammar is configured, not hardcoded, so a project that names work items
differently still routes correctly.
"""

from harness.routing.chain import parent_chain, parse_work_id
from harness.routing.resolve import ResolvedContext, resolve_context

__all__ = ["ResolvedContext", "parent_chain", "parse_work_id", "resolve_context"]
