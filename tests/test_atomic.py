"""Failure injection for canonical writes and recoverable component publication."""
from pathlib import Path

import pytest

from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.models.common import BlobRef, SourceRef
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.atomic import (
    ArchiveTransaction,
    recover_archive_writes,
    require_settled_archive,
)
from wikidot_backup.util.hashing import sha256_bytes, sha256_text


def test_page_publication_failure_restores_previous_pair(client, page_data, tmp_path, monkeypatch):
    writer = ArchiveWriter(tmp_path)
    writer.save_page(*collect_page(client, "test-page"))
    directory = tmp_path / "pages/123"
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    client.fetch_page.return_value = page_data(source="changed")
    replace = Path.replace

    def fail_metadata(path, target):
        if path.suffix == ".new" and Path(target).name == "page.json":
            raise OSError("publication failed")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_metadata)
    with pytest.raises(OSError, match="publication failed"):
        writer.save_page(*collect_page(client, "test-page"))
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == original
    require_settled_archive(tmp_path)


def test_process_interruption_is_detected_and_recovered(tmp_path, monkeypatch):
    old = tmp_path / "pages/123/source.txt"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    transaction = ArchiveTransaction(tmp_path)
    transaction.stage("pages/123/source.txt", b"new")
    transaction.stage("pages/123/page.json", b"new metadata")
    replace = Path.replace

    def stop_mid_commit(path, target):
        if path.name == "1.new":
            raise KeyboardInterrupt
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", stop_mid_commit)
    # Deliberately omit __exit__, simulating termination before cleanup can run.
    with pytest.raises(KeyboardInterrupt):
        transaction.commit()
    assert old.read_bytes() == b"new"
    with pytest.raises(RuntimeError, match="Interrupted archive write"):
        require_settled_archive(tmp_path)
    recover_archive_writes(tmp_path)
    assert old.read_bytes() == b"old"
    assert not (old.parent / "page.json").exists()
    require_settled_archive(tmp_path)


def revision(source, revision_id=1):
    return PageRevisionRecord(
        page_id=123,
        revision_id=revision_id,
        revision_no=revision_id - 1,
        source=SourceRef(
            path=f"revisions/sources/{revision_id}.txt",
            sha256=sha256_text(source),
            characters=len(source),
        ),
    ), source


def test_failed_revision_iterator_preserves_existing_history(tmp_path):
    writer = ArchiveWriter(tmp_path)
    writer.save_page_revisions(123, [revision("old")])
    directory = tmp_path / "pages/123/revisions"
    original = {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }

    def broken():
        yield revision("changed")
        raise RuntimeError("crawl failed")

    with pytest.raises(RuntimeError, match="crawl failed"):
        writer.save_page_revisions(123, broken())
    assert {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    } == original


def test_corrupted_existing_blob_is_not_silently_reused(tmp_path):
    content = b"correct"
    digest = sha256_bytes(content)
    blob = BlobRef(path=f"blobs/sha256/{digest}", sha256=digest, size=len(content))
    path = tmp_path / blob.path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="Corrupted existing blob"):
        ArchiveWriter(tmp_path).save_blob(blob, content)
    assert path.read_bytes() == b"corrupt"


def test_failed_recovery_retains_journal_for_retry(tmp_path, monkeypatch):
    path = tmp_path / "pages/123/source.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    transaction = ArchiveTransaction(tmp_path)
    transaction.stage("pages/123/source.txt", b"new")
    transaction.stage("pages/123/page.json", b"metadata")
    replace = Path.replace

    def fail_second_publication(source, target):
        if source.name == "1.new":
            raise KeyboardInterrupt
        return replace(source, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "replace", fail_second_publication)
        with pytest.raises(KeyboardInterrupt):
            transaction.commit()

    def disk_failure(source, target):
        raise OSError("disk unavailable")

    with monkeypatch.context() as context:
        context.setattr(Path, "replace", disk_failure)
        with pytest.raises(OSError):
            recover_archive_writes(tmp_path)
    assert (transaction.directory / "transaction.json").is_file()
    recover_archive_writes(tmp_path)
    assert path.read_bytes() == b"old"


def test_revision_publication_failure_restores_sources_and_metadata(tmp_path, monkeypatch):
    writer = ArchiveWriter(tmp_path)
    writer.save_page_revisions(123, [revision("old")])
    directory = tmp_path / "pages/123/revisions"
    old_metadata = (directory / "revisions.jsonl").read_bytes()
    replace = Path.replace

    def fail_metadata(source, target):
        if source.suffix == ".new" and Path(target).name == "revisions.jsonl":
            raise OSError("publish failed")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_metadata)
    with pytest.raises(OSError):
        writer.save_page_revisions(123, [revision("changed"), revision("extra", 2)])
    assert (directory / "sources/1.txt").read_bytes() == b"old"
    assert not (directory / "sources/2.txt").exists()
    assert (directory / "revisions.jsonl").read_bytes() == old_metadata
