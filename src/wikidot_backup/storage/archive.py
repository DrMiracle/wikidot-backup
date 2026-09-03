"""Filesystem writer for the portable backup archive."""
from __future__ import annotations

from pathlib import Path

from wikidot_backup.config import TEXT_ENCODING, TEXT_NEWLINE, SOURCE_FILENAME
from wikidot_backup.models.page import PageRecord


class ArchiveWriter:
    """Write normalized backup data to the filesystem archive."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save_page(
        self,
        page: PageRecord,
        source: str,
    ) -> Path:
        """Save page metadata and its current Wikidot source.

        The numeric Wikidot page ID is used as the directory name because
        it is stable and does not contain filesystem-unsafe category syntax.

        Args:
            page:
                Normalized persistent page metadata.

            source:
                Raw Wikidot source text.

        Returns:
            Directory in which the page was stored.
        """

        # Use page IDs instead of fullnames because fullnames may contain ':', which is not valid in Windows filenames.
        page_dir = self.root / "pages" / str(page.page_id)

        page_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        source_path = page_dir / SOURCE_FILENAME

        source_path.write_text(
            source,
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        )

        metadata_path = page_dir / "page.json"

        metadata_path.write_text(
            page.model_dump_json(
                indent=2,
                exclude_none=False,
            ),
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        )

        return page_dir
