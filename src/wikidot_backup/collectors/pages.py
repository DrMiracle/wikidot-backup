"""Collectors for individual Wikidot pages."""
from __future__ import annotations

from wikidot_backup.models.common import UserRef
from wikidot_backup.models.page import PageRecord, SourceRef
from wikidot_backup.util.hashing import sha256_text
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.models import WikidotUserData


def collect_page(
    client: WikidotClient,
    fullname: str,
) -> tuple[PageRecord, str]:
    """Collect and normalize one Wikidot page.

    The integration layer retrieves remote Wikidot data. This collector
    converts it into the project's persistent archive models and calculates
    integrity metadata for the raw page source.

    Args:
        client:
            Connected Wikidot client.

        fullname:
            Canonical Wikidot fullname of the page to collect.

    Returns:
        Tuple containing:

        - normalized persistent page metadata;
        - raw Wikidot source text.

        Source is returned separately because it is stored in ``source.txt``
        instead of being embedded directly in ``page.json``.
    """

    data = client.fetch_page(fullname)

    source_hash = sha256_text(
        data.source
    )

    page = PageRecord(
        page_id=data.page_id,

        fullname=data.fullname,
        name=data.name,
        category=data.category,
        title=data.title,

        parent_fullname=data.parent_fullname,

        tags=data.tags,
        hidden_tags=data.hidden_tags,

        children_count=data.children_count,
        comments_count=data.comments_count,

        size=data.size,

        rating=data.rating,
        votes_count=data.votes_count,
        rating_percent=data.rating_percent,

        latest_revision_no=data.latest_revision_no,

        created_by=_to_user_ref(data.created_by),
        created_at=data.created_at,

        updated_by=_to_user_ref(data.updated_by),
        updated_at=data.updated_at,

        commented_by=_to_user_ref(data.commented_by),
        commented_at=data.commented_at,

        discussion_thread_id=data.discussion_thread_id,

        metas=data.metas,

        # format, encoding and path use the archive-wide defaults
        # defined by SourceRef/config.py.
        source=SourceRef(
            sha256=source_hash,
            characters=len(data.source),
        ),
    )

    return page, data.source

def _to_user_ref(
    user: WikidotUserData | None,
) -> UserRef | None:
    """Convert integration-layer user data into archive user metadata."""

    if user is None:
        return None

    return UserRef(
        id=user.id,
        name=user.name,
        unix_name=user.unix_name,
    )
