"""Approximate backup size estimation."""
from __future__ import annotations

from dataclasses import dataclass

from wikidot_backup.config import TEXT_ENCODING
from wikidot_backup.services.backup_types import BackupOptions
from wikidot_backup.wikidot.client import WikidotClient


@dataclass(frozen=True, slots=True)
class BackupEstimate:
    """Approximate size information for a prospective backup."""

    pages: int

    current_source_bytes: int

    attachment_records: int
    attachment_reported_bytes: int
    attachments_with_unknown_size: int

    revision_records: int
    revision_source_estimated_bytes: int

    @property
    def estimated_total_bytes(self) -> int:
        """Return the estimated content size covered by this estimate."""
        return (
            self.current_source_bytes
            + self.attachment_reported_bytes
            + self.revision_source_estimated_bytes
        )


def estimate_backup(
    client: WikidotClient,
    *,
    options: BackupOptions,
    limit: int | None = None,
) -> BackupEstimate:
    """Estimate backup size without downloading attachment contents.

    Current page source sizes are measured from retrieved UTF-8 source.
    Attachment sizes use metadata reported by Wikidot.

    Historical revision source size is estimated by assuming that each
    revision is approximately the size of the current page source.

    Args:
        client:
            Connected Wikidot integration client.
        options:
            Components that would be included in the backup.
        limit:
            Optional maximum number of pages to inspect.

    Returns:
        Aggregate estimate for the selected pages.
    """
    fullnames = client.list_page_fullnames()

    if limit is not None:
        fullnames = fullnames[:limit]

    current_source_bytes = 0

    attachment_records = 0
    attachment_reported_bytes = 0
    attachments_with_unknown_size = 0

    revision_records = 0
    revision_source_estimated_bytes = 0

    for fullname in fullnames:
        page = client.fetch_page(fullname)

        source_bytes = len(
            page.source.encode(TEXT_ENCODING)
        )
        current_source_bytes += source_bytes

        if options.include_files:
            files = client.fetch_page_files(
                fullname
            )

            for file in files:
                attachment_records += 1

                if file.size is None:
                    attachments_with_unknown_size += 1
                else:
                    attachment_reported_bytes += file.size

        if options.include_revisions:
            # Wikidot revision numbering starts at 0. The value exposed
            # by page metadata is therefore the latest revision number,
            # not the number of stored revision versions.
            revision_count = page.latest_revision_no + 1

            revision_records += revision_count

            # Historical source sizes are unavailable without fetching
            # every revision, so use the current source as a heuristic.
            revision_source_estimated_bytes += (source_bytes * revision_count)

    return BackupEstimate(
        pages=len(fullnames),
        current_source_bytes=current_source_bytes,
        attachment_records=attachment_records,
        attachment_reported_bytes=(
            attachment_reported_bytes
        ),
        attachments_with_unknown_size=(
            attachments_with_unknown_size
        ),
        revision_records=revision_records,
        revision_source_estimated_bytes=(
            revision_source_estimated_bytes
        ),
    )
