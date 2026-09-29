"""Filesystem writer for the portable backup archive."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from wikidot_backup.config import SOURCE_FILENAME, TEXT_ENCODING, TEXT_NEWLINE
from wikidot_backup.models.common import BlobRef
from wikidot_backup.models.file import PageFileRecord, PageFilesRecord
from wikidot_backup.models.page import PageRecord
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.storage.atomic import ArchiveTransaction, archive_path, atomic_write
from wikidot_backup.util.hashing import sha256_bytes, sha256_text


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

        # Numeric IDs remain stable and avoid Windows-unsafe fullname characters.
        page_dir = self.root / "pages" / str(page.page_id)

        page_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if page.source.path != SOURCE_FILENAME or sha256_text(source) != page.source.sha256:
            raise ValueError("Page source reference does not match supplied source.")

        with ArchiveTransaction(self.root) as transaction:
            transaction.stage(
                f"pages/{page.page_id}/{SOURCE_FILENAME}", source.encode(TEXT_ENCODING),
            )
            transaction.stage(
                f"pages/{page.page_id}/page.json",
                page.model_dump_json(indent=2, exclude_none=False).encode(TEXT_ENCODING),
            )
            transaction.commit()

        return page_dir

    def save_page_revisions(
            self,
            page_id: int,
            revisions: Iterable[tuple[PageRevisionRecord, str]],
    ) -> int:
        """Write complete revision history for one archived page.

        Sources are staged as collected. Canonical files are published only
        after the complete iterator finishes, retaining rollback copies.
        Metadata is written oldest first, ordered by Wikidot revision number.

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
        with ArchiveTransaction(self.root) as transaction:
            for record, source in revisions:
                expected = f"revisions/sources/{record.revision_id}.txt"
                if (record.page_id != page_id or record.source.path != expected
                        or record.source.sha256 != sha256_text(source)):
                    raise ValueError("Revision source reference does not match supplied source.")

                transaction.stage(f"pages/{page_id}/{expected}", source.encode(TEXT_ENCODING))
                records.append(record)

            # Remote enumeration order varies; make the archive easy to read.
            records.sort(key=lambda record: record.revision_no)

            transaction.stage(
                f"pages/{page_id}/revisions/revisions.jsonl",
                "".join(r.model_dump_json() + TEXT_NEWLINE for r in records).encode(TEXT_ENCODING),
            )
            transaction.commit()

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
            if record.page_id != page_id or record.content is None:
                raise ValueError("Attachment must have matching page identity and content.")

            self.save_blob(
                record.content,
                content,
            )

            records.append(record)

        metadata = PageFilesRecord(
            page_id=page_id,
            files=records,
        )

        metadata_path = page_dir / "files.json"

        atomic_write(
            metadata_path,
            (metadata.model_dump_json(indent=2) + TEXT_NEWLINE).encode(TEXT_ENCODING),
        )

        return len(records)

    def save_blob(
            self,
            blob: BlobRef,
            content: bytes,
    ) -> None:
        """Persist immutable binary content atomically.

        Existing content-addressed blobs are reused instead of being written
        again. New blobs become visible at their canonical path only after the
        complete write succeeds.
        """
        if len(content) != blob.size:
            raise ValueError(
                "Blob size does not match supplied content."
            )

        if sha256_bytes(content) != blob.sha256 or blob.path != f"blobs/sha256/{blob.sha256}":
            raise ValueError("Blob hash or path does not match supplied content.")
        path = archive_path(self.root, blob.path)

        if path.is_file():
            if path.stat().st_size != blob.size or sha256_bytes(path.read_bytes()) != blob.sha256:
                raise RuntimeError(f"Corrupted existing blob: {path}")
            return

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        atomic_write(path, content)
