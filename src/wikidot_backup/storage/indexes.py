"""Derived indexes for navigating archived Wikidot data."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from wikidot_backup.config import (
    TEXT_ENCODING,
    TEXT_NEWLINE,
)
from wikidot_backup.models.page import PageRecord


@dataclass(frozen=True, slots=True)
class PageIndexEntry:
    """Human- and machine-readable reference to an archived page."""

    page_id: int
    fullname: str
    title: str | None
    category: str
    path: str


def rebuild_page_indexes(root: Path) -> int:
    """Rebuild page indexes from archived page metadata.

    The page directories remain the authoritative storage. Indexes are
    derived from ``pages/*/page.json`` and can therefore be safely rebuilt
    at any time.

    Args:
        root:
            Root directory of the backup archive.

    Returns:
        Number of archived pages included in the generated indexes.
    """
    pages_dir = root / "pages"
    indexes_dir = root / "indexes"

    indexes_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    entries: list[PageIndexEntry] = []

    if pages_dir.exists():
        for metadata_path in pages_dir.glob("*/page.json"):
            page = PageRecord.model_validate_json(
                metadata_path.read_text(
                    encoding=TEXT_ENCODING,
                )
            )

            page_dir = metadata_path.parent

            entries.append(
                PageIndexEntry(
                    page_id=page.page_id,
                    fullname=page.fullname,
                    title=page.title,
                    category=page.category,

                    # Archive paths use POSIX separators even when the
                    # backup itself is created on Windows.
                    path=page_dir.relative_to(root).as_posix(),
                )
            )

    # Stable ordering makes indexes easier to inspect and compare.
    entries.sort(
        key=lambda entry: (
            entry.fullname.casefold(),
            entry.fullname,
        )
    )

    _write_json_index(
        indexes_dir / "pages.json",
        entries,
    )

    _write_csv_index(
        indexes_dir / "pages.csv",
        entries,
    )

    return len(entries)


def _write_json_index(
    path: Path,
    entries: list[PageIndexEntry],
) -> None:
    """Write the machine-readable page index."""

    data = {
        "schema_version": 1,
        "page_count": len(entries),
        "pages": [
            asdict(entry)
            for entry in entries
        ],
    }

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding=TEXT_ENCODING,
        newline=TEXT_NEWLINE,
    )


def _write_csv_index(
    path: Path,
    entries: list[PageIndexEntry],
) -> None:
    """Write the human-readable page index."""

    with path.open(
        "w",
        encoding=TEXT_ENCODING,
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "page_id",
                "fullname",
                "title",
                "category",
                "path",
            ],
            lineterminator=TEXT_NEWLINE,
        )

        writer.writeheader()

        for entry in entries:
            writer.writerow(
                asdict(entry)
            )
