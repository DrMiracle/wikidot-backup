"""Filesystem writer for the portable backup archive."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from wikidot_backup.config import TEXT_ENCODING, TEXT_NEWLINE, SOURCE_FILENAME
from wikidot_backup.models.file import PageFileRecord, PageFilesRecord
from wikidot_backup.models.page import PageRecord
from wikidot_backup.models.revision import PageRevisionRecord


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

    def save_page_revisions(
            self,
            page_id: int,
            revisions: Iterable[tuple[PageRevisionRecord, str]],
    ) -> int:
        """Write complete revision history for one archived page.

        Revision sources are written as they are collected. The metadata JSONL
        file is written only after the complete revision iterator finishes.

        Args:
            page_id:
                Stable Wikidot page identifier.
            revisions:
                Revision metadata/source pairs.

        Returns:
            Number of revision records written.
        """
        page_dir = self.root / "pages" / str(page_id)
        revisions_dir = page_dir / "revisions"

        revisions_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        records: list[PageRevisionRecord] = []

        for record, source in revisions:
            source_path = page_dir / record.source.path
            source_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            source_path.write_text(
                source,
                encoding=TEXT_ENCODING,
                newline=TEXT_NEWLINE,
            )

            records.append(record)

        metadata_path = revisions_dir / "revisions.jsonl"

        with metadata_path.open(
                "w",
                encoding=TEXT_ENCODING,
                newline=TEXT_NEWLINE,
        ) as file:
            for record in records:
                file.write(
                    record.model_dump_json(
                        exclude_none=False
                    )
                )
                file.write(TEXT_NEWLINE)

        return len(records)

    def save_page_files(
            self,
            page_id: int,
            files: Iterable[
                tuple[PageFileRecord, bytes]
            ],
    ) -> int:
        """Persist page attachment metadata and original binary contents.

        Binary data is stored by SHA-256 digest, allowing identical attachment
        content to be shared safely across multiple page records.

        Args:
            page_id:
                Stable Wikidot page identifier.
            files:
                Attachment metadata/content pairs.

        Returns:
            Number of attachment records written.
        """
        page_dir = (
                self.root
                / "pages"
                / str(page_id)
        )
        page_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        records: list[PageFileRecord] = []

        for record, content in files:
            blob_path = (
                    self.root / record.content.path
            )

            blob_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            # Content-addressed blobs are immutable. If the same checksum is
            # already present, the existing binary data can be reused.
            # Verifying integrity can be improved in the future by comparing sha256.
            if not blob_path.exists():
                blob_path.write_bytes(content)

            records.append(record)

        metadata = PageFilesRecord(
            page_id=page_id,
            files=records,
        )

        metadata_path = page_dir / "files.json"

        metadata_path.write_text(
            metadata.model_dump_json(
                indent=2,
                exclude_none=False,
            ),
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        )

        return len(records)
