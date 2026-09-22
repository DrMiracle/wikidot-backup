"""Atomic individual writes and recoverable groups of canonical file replacements."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, ConfigDict, StrictBool

from wikidot_backup.config import TEXT_ENCODING


def archive_path(root: Path, relative: str) -> Path:
    """Resolve an archive-relative path without allowing escape from its root."""
    path = Path(relative)

    if path.is_absolute() or path.drive or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid archive-relative path: {relative!r}")

    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Archive path escapes its root: {relative!r}")

    return target


def atomic_write(path: Path, content: bytes) -> None:
    """Flush a complete file before replacing its canonical destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class _Replacement(BaseModel):
    """One old canonical file retained until an entire replacement commits."""

    model_config = ConfigDict(extra="forbid")
    path: str
    existed: StrictBool


class ArchiveTransaction:
    """Stage a component and retain rollback copies during publication.

    Separate files cannot be replaced atomically together. A journal makes an
    interrupted publication detectable and recoverable on the next backup.
    Only one process may write an archive at a time.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        directory = root / ".state" / "transactions"
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="write-", dir=directory))
        self.records: list[_Replacement] = []

    def __enter__(self) -> ArchiveTransaction:
        return self

    def stage(self, relative: str, content: bytes) -> None:
        """Stage bytes while leaving canonical files untouched."""
        path = archive_path(self.root, relative)
        if any(record.path == relative for record in self.records):
            raise ValueError(f"Duplicate transaction destination: {relative}")

        index = len(self.records)
        atomic_write(self.directory / f"{index}.new", content)
        existed = path.exists()

        if existed:
            atomic_write(self.directory / f"{index}.old", path.read_bytes())

        self.records.append(_Replacement(path=relative, existed=existed))

    def commit(self) -> None:
        """Publish all staged files, retaining rollback data until completion."""
        journal = self.directory / "transaction.json"
        atomic_write(
            journal, json.dumps([r.model_dump() for r in self.records]).encode(TEXT_ENCODING)
        )

        for index, record in enumerate(self.records):
            destination = archive_path(self.root, record.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            (self.directory / f"{index}.new").replace(destination)

        # Removing the journal is the commit point. Cleanup can safely be retried.
        journal.unlink()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _recover_transaction(self.root, self.directory)


def _recover_transaction(root: Path, directory: Path) -> None:
    """Rollback an interrupted publication; keep the journal if recovery fails."""
    transaction_root = (root / ".state" / "transactions").resolve()
    if (
        directory.resolve().parent != transaction_root
        or directory.is_symlink()
        or not directory.name.startswith("write-")
        or not directory.is_dir()
    ):
        raise RuntimeError(f"Invalid transaction directory: {directory}")

    journal = directory / "transaction.json"
    if journal.exists():
        raw = json.loads(journal.read_text(encoding=TEXT_ENCODING))
        if not isinstance(raw, list):
            raise RuntimeError(f"Invalid transaction journal: {journal}")

        records = [_Replacement.model_validate(item) for item in raw]
        # Validate every destination and backup before starting restoration.
        destinations = [archive_path(root, record.path) for record in records]

        for index, record in enumerate(records):
            if record.existed and not (directory / f"{index}.old").is_file():
                raise RuntimeError(f"Missing transaction recovery data: {directory}")

        for index, (record, destination) in enumerate(zip(records, destinations, strict=True)):
            if record.existed:
                atomic_write(destination, (directory / f"{index}.old").read_bytes())
            else:
                destination.unlink(missing_ok=True)

        journal.unlink()

    # The directory was allocated by this module; do not recursively delete it.
    for child in directory.iterdir():
        if child.is_dir():
            raise RuntimeError(f"Unexpected transaction contents: {child}")
        child.unlink()

    directory.rmdir()


def recover_archive_writes(root: Path) -> None:
    """Recover staged/interrupted writes after validating the archive identity."""
    directory = root / ".state" / "transactions"
    if directory.exists():
        for transaction in directory.iterdir():
            _recover_transaction(root, transaction)


def require_settled_archive(root: Path) -> None:
    """Keep read-only inspection from interpreting a partially published component."""
    if any((root / ".state" / "transactions").glob("*/transaction.json")):
        raise RuntimeError("Interrupted archive write; rerun backup to recover before inspection.")
