"""Persistent models for archived Wikidot page revisions."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from wikidot_backup.models.common import SourceRef, UserRef


class PageRevisionRecord(BaseModel):
    """Persistent archive representation of one Wikidot page revision."""

    schema_version: int = 1

    page_id: int

    revision_id: int
    revision_no: int

    created_by: UserRef | None = None
    created_at: datetime | None = None

    comment: str | None = None

    source: SourceRef
