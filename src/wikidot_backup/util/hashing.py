"""Helpers for calculating archive integrity hashes."""
import hashlib

from wikidot_backup.config import TEXT_ENCODING


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of text encoded with the archive encoding."""

    return hashlib.sha256(text.encode(TEXT_ENCODING)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 digest of raw binary data."""

    return hashlib.sha256(data).hexdigest()
