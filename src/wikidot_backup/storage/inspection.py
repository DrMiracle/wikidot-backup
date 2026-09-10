"""Inspection of an existing filesystem archive."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from wikidot_backup.config import TEXT_ENCODING
from wikidot_backup.models.file import PageFilesRecord
from wikidot_backup.models.page import PageRecord


@dataclass(frozen=True, slots=True)
class ArchiveInfo:
    """Statistics calculated from archive contents."""

    pages: int
    current_sources: int

    pages_with_file_metadata: int
    file_records: int
    unique_blobs: int

    pages_with_revisions: int
    revisions: int

    resume_present: bool
    resume_pages: int
    error_records: int

    pages_bytes: int
    blobs_bytes: int
    indexes_bytes: int
    state_bytes: int
    total_bytes: int


def inspect_archive(
        root: Path,
) -> ArchiveInfo:
    """Calculate statistics from files physically present in an archive."""
    if not root.is_dir():
        raise FileNotFoundError(
            f"Archive directory not found: {root}"
        )

    pages_dir = root / "pages"
    blobs_dir = root / "blobs" / "sha256"
    resume_path = root / ".state" / "resume.jsonl"

    pages = 0
    current_sources = 0

    pages_with_file_metadata = 0
    file_records = 0

    pages_with_revisions = 0
    revisions = 0

    if pages_dir.is_dir():
        for metadata_path in pages_dir.glob(
                "*/page.json"
        ):
            page_dir = metadata_path.parent

            try:
                page = PageRecord.model_validate_json(
                    metadata_path.read_text(
                        encoding=TEXT_ENCODING,
                    )
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Invalid page metadata: {metadata_path}"
                ) from exc

            pages += 1

            if (
                    page_dir / page.source.path
            ).is_file():
                current_sources += 1

            files_path = page_dir / "files.json"

            if files_path.is_file():
                try:
                    files_record = (
                        PageFilesRecord.model_validate_json(
                            files_path.read_text(
                                encoding=TEXT_ENCODING,
                            )
                        )
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"Invalid attachment metadata: {files_path}"
                    ) from exc

                pages_with_file_metadata += 1
                file_records += len(
                    files_record.files
                )

            revisions_path = (
                    page_dir
                    / "revisions"
                    / "revisions.jsonl"
            )

            if revisions_path.is_file():
                pages_with_revisions += 1
                revisions += _count_nonempty_lines(
                    revisions_path
                )

    unique_blobs = (
        sum(
            1
            for path in blobs_dir.iterdir()
            if path.is_file()
        )
        if blobs_dir.is_dir()
        else 0
    )

    return ArchiveInfo(
        pages=pages,
        current_sources=current_sources,
        pages_with_file_metadata=(
            pages_with_file_metadata
        ),
        file_records=file_records,
        unique_blobs=unique_blobs,
        pages_with_revisions=pages_with_revisions,
        revisions=revisions,
        resume_present=resume_path.is_file(),
        resume_pages=_count_unique_resume_pages(
            resume_path
        ),
        error_records=_count_nonempty_lines(
            root / ".state" / "errors.jsonl"
        ),
        pages_bytes=_directory_size(
            root / "pages"
        ),
        blobs_bytes=_directory_size(
            root / "blobs"
        ),
        indexes_bytes=_directory_size(
            root / "indexes"
        ),
        state_bytes=_directory_size(
            root / ".state"
        ),
        total_bytes=_directory_size(root),
    )


def _count_nonempty_lines(
        path: Path,
) -> int:
    """Count non-empty records in a line-oriented file."""
    if not path.is_file():
        return 0

    with path.open(
            "r",
            encoding=TEXT_ENCODING,
    ) as file:
        return sum(
            1
            for line in file
            if line.strip()
        )


def _count_unique_resume_pages(
        path: Path,
) -> int:
    """Count unique pages represented in resume state."""
    if not path.is_file():
        return 0

    fullnames: set[str] = set()

    with path.open(
            "r",
            encoding=TEXT_ENCODING,
    ) as file:
        for line_number, line in enumerate(
                file,
                start=1,
        ):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid resume state in {path} "
                    f"at line {line_number}."
                ) from exc

            fullname = record.get("fullname")

            if isinstance(fullname, str):
                fullnames.add(fullname)

    return len(fullnames)


def _directory_size(
        path: Path,
) -> int:
    """Return total byte size of regular files below a path."""
    if not path.exists():
        return 0

    if path.is_file():
        return path.stat().st_size

    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file()
    )
