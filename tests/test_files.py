from __future__ import annotations

from unittest.mock import Mock

from wikidot_backup.collectors.files import collect_page_files
from wikidot_backup.models.common import BlobRef
from wikidot_backup.models.file import PageFileRecord, PageFilesRecord
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.util.hashing import sha256_bytes
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.models import WikidotFileData


def test_collect_page_files_preserves_original_bytes() -> None:
    """Collected attachment content must remain byte-for-byte unchanged."""
    content = b"\xff\xd8\xff\xe0test-jpeg-data"

    client = Mock(spec=WikidotClient)
    client.fetch_page_files.return_value = [
        WikidotFileData(
            file_id=123,
            name="example.jpg",
            url="https://example.com/example.jpg",
            mime_type="image/jpeg",
            size=100,
        )
    ]
    client.fetch_file_content.return_value = content

    result = list(
        collect_page_files(
            client,
            page_id=456,
            fullname="example-page",
        )
    )

    assert len(result) == 1

    record, archived_content = result[0]

    assert archived_content == content

    assert record.file_id == 123
    assert record.page_id == 456
    assert record.name == "example.jpg"

    # Wikidot's reported size is metadata and may differ from the
    # number of bytes actually returned by the attachment endpoint.
    assert record.wikidot_size == 100
    assert record.content.size == len(content)

    assert record.content.sha256 == sha256_bytes(
        content
    )


def test_save_page_files_creates_empty_metadata(
    tmp_path,
) -> None:
    """Pages without attachments should still complete the FILES component."""
    writer = ArchiveWriter(tmp_path)

    count = writer.save_page_files(
        page_id=123,
        files=[],
    )

    assert count == 0

    metadata_path = (
        tmp_path
        / "pages"
        / "123"
        / "files.json"
    )

    assert metadata_path.is_file()

    metadata = PageFilesRecord.model_validate_json(
        metadata_path.read_text(
            encoding="utf-8",
        )
    )

    assert metadata.page_id == 123
    assert metadata.files == []


def test_save_page_files_stores_original_blob(
    tmp_path,
) -> None:
    """Attachment bytes should be stored unchanged under their SHA-256."""
    writer = ArchiveWriter(tmp_path)

    content = b"same binary content"
    checksum = sha256_bytes(content)

    record = PageFileRecord(
        page_id=123,
        file_id=1,
        name="example.bin",
        source_url="https://example.com/example.bin",
        mime_type="application/octet-stream",
        wikidot_size=len(content),
        content=BlobRef(
            path=f"blobs/sha256/{checksum}",
            sha256=checksum,
            size=len(content),
        ),
    )

    writer.save_page_files(
        123,
        [(record, content)],
    )

    blob_path = (
        tmp_path
        / "blobs"
        / "sha256"
        / checksum
    )

    assert blob_path.read_bytes() == content


def test_identical_attachments_share_one_blob(
    tmp_path,
) -> None:
    """Identical attachment contents should not create duplicate blobs."""
    writer = ArchiveWriter(tmp_path)

    content = b"shared content"
    checksum = sha256_bytes(content)

    def make_record(
        file_id: int,
        name: str,
    ) -> PageFileRecord:
        return PageFileRecord(
            page_id=123,
            file_id=file_id,
            name=name,
            source_url=f"https://example.com/{name}",
            content=BlobRef(
                path=f"blobs/sha256/{checksum}",
                sha256=checksum,
                size=len(content),
            ),
        )

    writer.save_page_files(
        123,
        [
            (
                make_record(1, "first.bin"),
                content,
            ),
            (
                make_record(2, "second.bin"),
                content,
            ),
        ],
    )

    blobs = list(
        (tmp_path / "blobs" / "sha256").iterdir()
    )

    assert len(blobs) == 1
    assert blobs[0].read_bytes() == content
