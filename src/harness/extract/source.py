"""Read committed git bytes and turn them into the normalized model.

Git is the source of truth and Postgres is derived, so extraction must read the
repository's *committed* content — never the working tree. An uncommitted edit
must not be visible to the index, or the index would encode a fact that git does
not hold.

The bytes are materialized from `git archive <rev>` into a temporary directory,
which is then handed to the tested `harness.okf.reader`. The temp directory is
only a rendering of committed content; it is never a source of truth. This is
what keeps `reader.py` reused rather than rewritten.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from harness.extract.documents import extract_documents, extract_registry_tables
from harness.extract.model import MODEL_VERSION, IndexModel
from harness.okf import Bundle

if TYPE_CHECKING:
    from harness.config import Config


class IndexSourceError(Exception):
    """Raised when the git source cannot be read."""


def repo_root(root: Path | None = None) -> Path:
    """The repository the command was invoked in, not the package's location.

    Kept identical to `guards/session.py` and `entries/commits.py` on purpose:
    resolving a caller's context from the library's own directory is the defect
    this project has hit more than once.
    """
    return (root or Path.cwd()).resolve()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, check=False
    )


def commit_sha(root: Path, rev: str = "HEAD") -> str:
    """Resolve `rev` to a full commit SHA, failing loudly when it does not exist."""
    proc = _git(root, "rev-parse", "--verify", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "unknown git error"
        raise IndexSourceError(f"cannot resolve {rev!r} in {root}: {detail}")
    return proc.stdout.decode().strip()


@contextmanager
def materialize_commit(root: Path, rev: str = "HEAD") -> Iterator[Path]:
    """Yield a directory containing exactly the files committed at `rev`.

    `git archive` is used rather than a working-tree walk so that uncommitted
    changes, untracked files and ignored files are all absent by construction.
    """
    sha = commit_sha(root, rev)
    proc = _git(root, "archive", "--format=tar", sha)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "unknown git error"
        raise IndexSourceError(f"cannot archive {rev!r} in {root}: {detail}")

    with tempfile.TemporaryDirectory(prefix="mrb-harness-index-") as tmp:
        target = Path(tmp)
        try:
            with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as archive:
                archive.extractall(target, filter="data")
        except tarfile.TarError as exc:  # pragma: no cover - malformed git output
            raise IndexSourceError(f"unreadable archive for {rev!r}: {exc}") from exc
        yield target


def model_from_git(root: Path, config: Config, rev: str = "HEAD") -> IndexModel:
    """Build the normalized model for one git revision.

    This is a pure function of the committed bytes at `rev`: two calls with the
    same arguments produce models with the same digest.
    """
    root = repo_root(root)
    sha = commit_sha(root, rev)
    knowledge = Path(config.paths.knowledge)

    with materialize_commit(root, rev) as tree:
        bundle_root = tree / knowledge
        documents = []
        if bundle_root.is_dir():
            documents = extract_documents(Bundle(bundle_root), tree)

        registry_paths = [str(reg.path) for reg in config.registries.values()]
        registry_tables = extract_registry_tables(tree, registry_paths)

    return IndexModel(
        project=config.identity.name,
        commit_sha=sha,
        source_rev=rev,
        model_version=MODEL_VERSION,
        documents=tuple(documents),
        registry_tables=tuple(registry_tables),
    )
