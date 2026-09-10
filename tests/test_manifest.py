"""Tests for archive manifest storage."""

from pathlib import Path

import pytest

from wikidot_backup.models.manifest import ArchiveSite
from wikidot_backup.storage.manifest import (
    ArchiveManifestStore,
)


def make_site(
    *,
    site_id: int = 123,
    unix_name: str = "example",
) -> ArchiveSite:
    """Create Wikidot site metadata for manifest tests."""
    return ArchiveSite(
        id=site_id,
        unix_name=unix_name,
        title="Example site",
        domain=f"{unix_name}.wikidot.com",
        url=f"http://{unix_name}.wikidot.com",
    )


def test_manifest_is_created(
    tmp_path: Path,
) -> None:
    """A new archive should receive root identity metadata."""
    store = ArchiveManifestStore(tmp_path)

    manifest = store.ensure_archive(
        make_site()
    )

    assert (
        tmp_path / "archive.json"
    ).is_file()

    assert manifest.schema_version == 1
    assert manifest.archive_format == "scp-wikidot-backup"
    assert manifest.site.id == 123
    assert manifest.site.unix_name == "example"

    assert manifest.last_successful_run_at is None
    assert manifest.last_full_backup_at is None


def test_existing_manifest_keeps_creation_time(
    tmp_path: Path,
) -> None:
    """Opening the same archive should not recreate its identity."""
    store = ArchiveManifestStore(tmp_path)

    first = store.ensure_archive(
        make_site()
    )
    second = store.ensure_archive(
        make_site()
    )

    assert second.created_at == first.created_at


def test_different_site_is_rejected(
    tmp_path: Path,
) -> None:
    """One archive directory must never mix different Wikidot sites."""
    store = ArchiveManifestStore(tmp_path)

    store.ensure_archive(
        make_site()
    )

    with pytest.raises(
        RuntimeError,
        match="different Wikidot site",
    ):
        store.ensure_archive(
            make_site(
                site_id=456,
                unix_name="other",
            )
        )


def test_limited_success_does_not_mark_full_backup(
    tmp_path: Path,
) -> None:
    """A successful partial run should not become a full backup."""
    store = ArchiveManifestStore(tmp_path)

    store.ensure_archive(
        make_site()
    )

    store.record_success(
        components=[
            "page",
            "files",
        ],
        full_backup=False,
    )

    manifest = store.load()

    assert manifest.last_successful_run_at is not None
    assert manifest.last_full_backup_at is None

    # Stored deterministically regardless of caller order.
    assert manifest.last_successful_components == [
        "files",
        "page",
    ]


def test_full_success_marks_full_backup(
    tmp_path: Path,
) -> None:
    """A successful complete crawl should record full completion."""
    store = ArchiveManifestStore(tmp_path)

    store.ensure_archive(
        make_site()
    )

    store.record_success(
        components=[
            "page",
            "files",
            "revisions",
        ],
        full_backup=True,
    )

    manifest = store.load()

    assert manifest.last_successful_run_at is not None
    assert manifest.last_full_backup_at is not None


def test_limited_run_does_not_erase_previous_full_backup(
    tmp_path: Path,
) -> None:
    """A later limited run must preserve the last full backup timestamp."""
    store = ArchiveManifestStore(tmp_path)

    store.ensure_archive(
        make_site()
    )

    store.record_success(
        components=["page", "files"],
        full_backup=True,
    )

    first = store.load()
    full_backup_at = first.last_full_backup_at

    store.record_success(
        components=["page"],
        full_backup=False,
    )

    second = store.load()

    assert second.last_full_backup_at == full_backup_at
    assert second.last_successful_run_at is not None
