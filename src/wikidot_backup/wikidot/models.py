"""Normalized data structures returned by the Wikidot integration layer."""
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class WikidotUserData:
    """Normalized Wikidot user information."""

    id: int | None
    name: str
    unix_name: str | None


@dataclass(slots=True)
class WikidotPageData:
    """
    Internal normalized representation of a page fetched from Wikidot.

    This model is part of the integration boundary and is never written
    directly to the backup archive.

    It is intentionally separate from PageRecord, which represents the
    persistent backup schema.
    """

    page_id: int

    fullname: str
    name: str
    category: str
    title: str | None

    parent_fullname: str | None

    tags: list[str]
    hidden_tags: list[str]

    children_count: int
    comments_count: int

    size: int

    rating: int | float | None
    votes_count: int | None
    rating_percent: float | None

    latest_revision_no: int | None

    created_by: WikidotUserData | None
    created_at: Any | None

    updated_by: WikidotUserData | None
    updated_at: Any | None

    commented_by: WikidotUserData | None
    commented_at: Any | None

    discussion_thread_id: int | None

    metas: dict[str, str]

    source: str
