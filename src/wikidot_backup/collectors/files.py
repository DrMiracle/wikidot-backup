"""Collectors for Wikidot page attachments."""
from __future__ import annotations

from collections.abc import Iterator

from wikidot_backup.models.common import BlobRef
from wikidot_backup.models.file import PageFileRecord
from wikidot_backup.util.hashing import sha256_bytes
from wikidot_backup.wikidot.client import WikidotClient


def collect_page_files(
    client: WikidotClient,
    *,
    page_id: int,
    fullname: str,
) -> Iterator[tuple[PageFileRecord, bytes]]:
    """Collect all attachments currently associated with a Wikidot page.

    Attachment bytes are downloaded one at a time so the entire file
    collection does not need to be retained in memory.

    Args:
        client:
            Connected Wikidot integration client.
        page_id:
            Stable numeric Wikidot page identifier.
        fullname:
            Canonical Wikidot page fullname.

    Yields:
        Persistent attachment metadata paired with original binary content.
    """
    files = client.fetch_page_files(
        fullname
    )

    for file in files:
        content = client.fetch_file_content(
            file.url
        )

        checksum = sha256_bytes(content)

        yield (
            PageFileRecord(
                page_id=page_id,
                file_id=file.file_id,
                name=file.name,
                source_url=file.url,
                mime_type=file.mime_type,
                wikidot_size=file.size,
                content=BlobRef(
                    path=(
                        "blobs/sha256/"
                        f"{checksum}"
                    ),
                    sha256=checksum,
                    size=len(content),
                ),
            ),
            content,
        )
