"""Reading and writing root archive metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from wikidot_backup.config import TEXT_ENCODING, TEXT_NEWLINE
from wikidot_backup.models.manifest import ArchiveManifest, ArchiveSite


class ArchiveManifestStore:
    """Manage root metadata for one backup archive."""

    def __init__(self, root: Path) -> None:
        """Initialize manifest storage for an archive root."""
        self.root = root
        self.path = root / "archive.json"

    def ensure_archive(
        self,
        site: ArchiveSite,
    ) -> ArchiveManifest:
        """Create the manifest or validate an existing archive identity.

        Existing archives must belong to the same Wikidot site. This
        prevents accidentally writing one site's backup into another
        site's archive directory.

        Args:
            site:
                Identity of the Wikidot site being archived.

        Returns:
            Existing or newly created archive manifest.

        Raises:
            RuntimeError:
                If the archive already belongs to another site.
        """
        if self.path.exists():
            manifest = self.load()

            if (
                    manifest.site.id != site.id or
                    manifest.site.unix_name != site.unix_name
            ):
                raise RuntimeError("Archive belongs to a different Wikidot site.")

            return manifest

        manifest = ArchiveManifest(
            site=site,
            created_at=self._utc_now(),
        )

        self._write(manifest)

        return manifest

    def load(self) -> ArchiveManifest:
        """Load and validate the archive manifest."""
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Archive manifest not found: "
                f"{self.path}"
            )

        return ArchiveManifest.model_validate_json(
            self.path.read_text(
                encoding=TEXT_ENCODING,
            )
        )

    def record_success(
        self,
        *,
        components: list[str],
        full_backup: bool,
    ) -> None:
        """Record successful completion of one backup invocation."""
        manifest = self.load()
        now = self._utc_now()

        updates: dict[str, object] = {
            "last_successful_run_at": now,
            "last_successful_components": sorted(
                components
            ),
        }

        if full_backup:
            updates["last_full_backup_at"] = now

        manifest = manifest.model_copy(
            update=updates
        )

        self._write(manifest)

    def _write(
        self,
        manifest: ArchiveManifest,
    ) -> None:
        """Write the manifest atomically."""
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.path.with_suffix(
            ".json.tmp"
        )

        temporary_path.write_text(
            manifest.model_dump_json(
                indent=2,
                exclude_none=False,
            )
            + TEXT_NEWLINE,
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        )

        temporary_path.replace(self.path)

    @staticmethod
    def _utc_now() -> datetime:
        """Return the current timezone-aware UTC timestamp."""
        return datetime.now(timezone.utc)
