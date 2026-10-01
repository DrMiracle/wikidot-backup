"""Portable names for derived exports; original names remain in metadata."""

import re
import unicodedata
from pathlib import PurePosixPath


def export_name(name: str, *, identifier: int, used: set[str]) -> str:
    """Allocate a Windows-safe name, resolving case-insensitive collisions."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = f"unnamed-{identifier}"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", cleaned.split(".")[0], re.I):
        cleaned = "_" + cleaned

    suffix = PurePosixPath(cleaned).suffix[:20]
    stem = cleaned[: -len(suffix)] if suffix else cleaned
    stem = stem[:100]
    candidate = stem + suffix
    counter = 0
    while unicodedata.normalize("NFC", candidate).casefold() in used:
        counter += 1
        discriminator = f"--{identifier}" + (f"-{counter}" if counter > 1 else "")
        candidate = stem + discriminator + suffix
    used.add(unicodedata.normalize("NFC", candidate).casefold())
    return candidate
