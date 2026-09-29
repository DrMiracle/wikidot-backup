"""Portable forum archive records. HTML is never labeled as Wikidot source."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StrictBool

from wikidot_backup.models.common import UserRef


class ForumPostRecord(BaseModel):
    """One current post, including its reply relationship and rendered content."""

    schema_version: Literal[1] = 1
    thread_id: PositiveInt
    post_id: PositiveInt
    parent_id: PositiveInt | None = None
    title: str
    created_at: datetime
    created_by: UserRef
    content_format: Literal["html"] = "html"
    html: str
    raw_source_status: Literal["not_available_via_public_endpoint"] = (
        "not_available_via_public_endpoint"
    )


class ForumRevisionRecord(BaseModel):
    """A rendered version; history_position is a zero-based, derived ordering."""

    schema_version: Literal[1] = 1
    thread_id: PositiveInt
    post_id: PositiveInt
    revision_id: PositiveInt
    history_position: int = Field(ge=0)
    title: str
    created_at: datetime
    created_by: UserRef
    content_format: Literal["html"] = "html"
    html: str
    raw_source_status: Literal["not_available_via_public_endpoint"] = (
        "not_available_via_public_endpoint"
    )


class ForumThreadRecord(BaseModel):
    """Latest observed thread; absent old posts remain in posts.jsonl."""

    schema_version: Literal[1] = 1
    thread_id: PositiveInt
    category_id: PositiveInt | None
    title: str
    created_at: datetime
    created_by: UserRef
    fetched_at: datetime
    reported_posts: int = Field(ge=0)
    observed_post_ids: list[PositiveInt]
    archived_page_ids: list[PositiveInt]
    revisions_included: bool
    # Original endpoint bodies preserve whitespace and metadata not yet normalized.
    responses: dict[str, str]


class ForumCategoryRecord(BaseModel):
    """Category membership refers to a position in this catalog's group list."""

    category_id: PositiveInt
    group_position: int = Field(ge=0)
    title: str
    description_html: str
    reported_threads: int = Field(ge=0)
    discovered_thread_ids: list[PositiveInt]


class ForumDiscoveryRecord(BaseModel):
    """An immutable catalog snapshot and explicit discovery discrepancies."""

    schema_version: Literal[1] = 1
    run_id: str | None = None
    fetched_at: datetime
    groups_html: list[str]
    categories: list[ForumCategoryRecord]
    index_html: str
    page_discussion_thread_ids: list[PositiveInt]
    warnings: list[str]


class ForumResumeRecord(BaseModel):
    """Independent operational state for completed thread snapshots."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    thread_id: int = Field(gt=0)
    revisions: StrictBool
