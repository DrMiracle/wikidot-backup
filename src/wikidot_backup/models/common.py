"""Common models shared by different archive entities."""
from __future__ import annotations

from pydantic import BaseModel


class UserRef(BaseModel):
    """Minimal persistent reference to a Wikidot user."""

    # System/deleted/special Wikidot users may not have a numeric ID.
    id: int | None = None

    name: str
    unix_name: str | None = None
