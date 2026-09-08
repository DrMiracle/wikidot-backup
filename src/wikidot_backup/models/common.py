"""Common models shared by different archive entities."""
from __future__ import annotations

from pydantic import BaseModel

from wikidot_backup.config import TEXT_ENCODING, SOURCE_FORMAT


class UserRef(BaseModel):
    """Minimal persistent reference to a Wikidot user."""

    # System/deleted/special Wikidot users may not have a numeric ID.
    id: int | None = None

    name: str
    unix_name: str | None = None


class SourceRef(BaseModel):
    """Reference to the raw Wikidot source stored in the archive."""

    format: str = SOURCE_FORMAT
    encoding: str = TEXT_ENCODING

    # Path is relative to the containing page directory.
    path: str

    sha256: str
    characters: int
