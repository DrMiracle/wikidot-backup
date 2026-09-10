"""Persistent metadata describing an archive."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ArchiveSite(BaseModel):
    """Identity of the Wikidot site represented by an archive."""

    id: int
    unix_name: str
    title: str | None = None
    domain: str
    url: str


class ArchiveManifest(BaseModel):
    """Root metadata for a Wikidot backup archive."""

    schema_version: int = 1
    archive_format: str = "scp-wikidot-backup"

    site: ArchiveSite

    created_at: datetime

    # Successful includes intentionally limited development runs.
    last_successful_run_at: datetime | None = None

    # Updated only after a successful run that processed the complete
    # discovered page set.
    last_full_backup_at: datetime | None = None

    last_successful_components: list[str] = Field(
        default_factory=list
    )
