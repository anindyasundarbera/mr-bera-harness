"""The derived PostgreSQL index for the extracted document model.

Git holds the facts; this package holds a rebuildable rendering of them. Nothing
here may become a second place a fact is authored.
"""

from harness.index.schema import DDL, DROP, INDEX_SCHEMA_VERSION
from harness.index.store import IndexUnavailableError, connect, read_model, reset, write_model

__all__ = [
    "DDL",
    "DROP",
    "INDEX_SCHEMA_VERSION",
    "IndexUnavailableError",
    "connect",
    "read_model",
    "reset",
    "write_model",
]
