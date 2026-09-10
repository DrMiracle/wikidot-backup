"""Persistent models for archived Wikidot attachments."""
from __future__ import annotations

from pydantic import BaseModel, Field

from wikidot_backup.models.common import BlobRef


class PageFileRecord(BaseModel):
    """Persistent archive representation of one Wikidot attachment."""

    schema_version: int = 1

    page_id: int
    file_id: int

    name: str
    source_url: str

    mime_type: str | None = None

    # Size reported by Wikidot. Actual archived byte size is stored
    # independently in BlobRef and may therefore be verified.
    wikidot_size: int | None = None

    content: BlobRef | None = None
    retrieval_error: str | None = None


class PageFilesRecord(BaseModel):
    """Persistent attachment collection for one archived page."""

    schema_version: int = 1

    page_id: int
    files: list[PageFileRecord] = Field(
        default_factory=list
    )
