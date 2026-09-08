"""Collectors for Wikidot page revision history."""
from __future__ import annotations

from collections.abc import Iterator

from wikidot_backup.collectors.common import user_to_ref
from wikidot_backup.models.common import SourceRef
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.util.hashing import sha256_text
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.models import (
    WikidotPageRevisionData,
)


def collect_page_revisions(
    client: WikidotClient,
    *,
    page_id: int,
    fullname: str,
) -> Iterator[tuple[PageRevisionRecord, str]]:
    """Collect all known revisions of one Wikidot page.

    Revision metadata is retrieved first. Individual source versions are
    then fetched lazily so that source text for the entire revision history
    does not need to be retained in memory at once.

    Args:
        client:
            Connected Wikidot integration client.
        page_id:
            Stable Wikidot page identifier.
        fullname:
            Current canonical Wikidot page fullname.

    Yields:
        Tuples containing persistent revision metadata and its raw source.
    """
    revisions = client.fetch_page_revisions(fullname)

    for revision in revisions:
        yield collect_page_revision(
            client,
            page_id=page_id,
            revision=revision,
        )


def collect_page_revision(
    client: WikidotClient,
    *,
    page_id: int,
    revision: WikidotPageRevisionData,
) -> tuple[PageRevisionRecord, str]:
    """Collect one Wikidot page revision and prepare it for archival."""
    source = client.fetch_revision_source(
        revision.revision_id
    )

    source_path = (
        f"revisions/sources/"
        f"{revision.revision_id}.txt"
    )

    record = PageRevisionRecord(
        page_id=page_id,
        revision_id=revision.revision_id,
        revision_no=revision.revision_no,
        created_by=user_to_ref(
            revision.created_by
        ),
        created_at=revision.created_at,
        comment=revision.comment,
        source=SourceRef(
            path=source_path,
            sha256=sha256_text(source),
            characters=len(source),
        ),
    )

    return record, source
