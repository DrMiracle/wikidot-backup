"""Models describing archived Wikidot pages."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from wikidot_backup.config import SOURCE_FORMAT, TEXT_ENCODING, SOURCE_FILENAME
from wikidot_backup.models.common import UserRef


class SourceRef(BaseModel):
    """Reference to the raw Wikidot source stored in the archive."""

    format: str = SOURCE_FORMAT
    encoding: str = TEXT_ENCODING
    path: str = SOURCE_FILENAME
    
    sha256: str
    characters: int


class PageRecord(BaseModel):
    """Persistent archive representation of a Wikidot page.

    Unlike WikidotPageData, which represents normalized data fetched from
    Wikidot, PageRecord defines the stable on-disk backup schema written to
    page.json.

    Changes to this model therefore represent changes to the archive format
    and may require a schema-version migration.
    """

    schema_version: int = 1

    page_id: int

    fullname: str
    name: str
    category: str
    title: str

    parent_fullname: str | None = None

    tags: list[str] = Field(default_factory=list)
    hidden_tags: list[str] = Field(default_factory=list)

    children_count: int
    comments_count: int

    size: int

    rating: int | float | None = None
    votes_count: int | None = None
    rating_percent: float | None = None

    # Wikidot revision numbering starts at 0, so this is not the same
    # as the total number of archived revision objects.
    latest_revision_no: int | None = None

    created_by: UserRef | None = None
    created_at: datetime | None = None

    updated_by: UserRef | None = None
    updated_at: datetime | None = None

    commented_by: UserRef | None = None
    commented_at: datetime | None = None

    discussion_thread_id: int | None = None

    metas: dict[str, str] = Field(default_factory=dict)

    source: SourceRef
