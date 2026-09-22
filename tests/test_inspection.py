"""Inspect real persistent records, including malformed archive/state inputs."""

import json

import pytest

from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.models.common import SourceRef
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.services.backup_types import BackupComponent
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.inspection import inspect_archive
from wikidot_backup.storage.state import BackupState, load_page_states
from wikidot_backup.util.hashing import sha256_text


def test_inspect_archive_counts_stored_data(tmp_path, client):
    writer = ArchiveWriter(tmp_path)
    writer.save_page(*collect_page(client, "test-page"))
    writer.save_page_files(123, [])
    source = "old source"
    writer.save_page_revisions(
        123,
        [
            (
                PageRevisionRecord(
                    page_id=123,
                    revision_id=1,
                    revision_no=0,
                    source=SourceRef(
                        path="revisions/sources/1.txt",
                        sha256=sha256_text(source),
                        characters=len(source),
                    ),
                ),
                source,
            )
        ],
    )
    state = BackupState(tmp_path)
    state.start_run()
    for component in (BackupComponent.PAGE, BackupComponent.FILES):
        state.record_component_completed(fullname="test-page", page_id=123, component=component)
    state.record_error(fullname="broken", exception=RuntimeError("offline"))
    result = inspect_archive(tmp_path)
    assert result.pages == result.current_sources == 1
    assert result.pages_with_file_metadata == 1 and result.file_records == 0
    assert result.pages_with_revisions == result.revisions == 1
    assert result.resume_present and result.resume_pages == 1
    assert result.error_records == 1
    assert result.total_bytes == sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())


def test_missing_optional_content_is_zero(tmp_path, client):
    ArchiveWriter(tmp_path).save_page(*collect_page(client, "test-page"))
    result = inspect_archive(tmp_path)
    assert result.pages == 1
    assert result.file_records == result.unique_blobs == result.revisions == 0
    assert not result.resume_present


@pytest.mark.parametrize("filename", ["page.json", "files.json", "revisions/revisions.jsonl"])
def test_invalid_metadata_is_rejected(tmp_path, client, filename):
    ArchiveWriter(tmp_path).save_page(*collect_page(client, "test-page"))
    path = tmp_path / "pages/123" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid"):
        inspect_archive(tmp_path)


@pytest.mark.parametrize(
    "record",
    [
        [],
        {},
        {"fullname": "test", "page_id": True},
        {"fullname": "test", "page_id": 123, "component": "unknown"},
        {"fullname": "test", "page_id": 123, "component": None},
        {"fullname": "", "page_id": 123},
    ],
)
def test_backup_and_inspection_share_strict_resume_validation(tmp_path, record):
    path = tmp_path / ".state/resume.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    for operation in (
        lambda: BackupState(tmp_path).load_page_states(),
        lambda: inspect_archive(tmp_path),
    ):
        with pytest.raises(RuntimeError, match="Invalid"):
            operation()


def test_legacy_state_is_supported_and_conflicts_rejected(tmp_path):
    path = tmp_path / "resume.jsonl"
    path.write_text('{"fullname":"test","page_id":123}\n', encoding="utf-8")
    assert load_page_states(path)["test"].completed_components == {BackupComponent.PAGE}
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"fullname":"test","page_id":456,"component":"files"}\n')
    with pytest.raises(RuntimeError, match="Conflicting page IDs"):
        load_page_states(path)


def test_inspection_counts_attachment_records_and_unique_blobs(tmp_path, client):
    from wikidot_backup.collectors.files import collect_page_files
    from wikidot_backup.wikidot.models import WikidotFileData

    writer = ArchiveWriter(tmp_path)
    writer.save_page(*collect_page(client, "test-page"))
    client.fetch_page_files.return_value = [
        WikidotFileData(i, f"file-{i}", f"https://example.test/{i}", None, None) for i in range(3)
    ]
    client.fetch_file_content.side_effect = [b"first", b"second", b"first"]
    writer.save_page_files(123, collect_page_files(client, page_id=123, fullname="test-page"))
    info = inspect_archive(tmp_path)
    assert info.file_records == 3
    assert info.unique_blobs == 2
    (tmp_path / "blobs/sha256/.interrupted.tmp").write_bytes(b"partial")
    assert inspect_archive(tmp_path).unique_blobs == 2


@pytest.mark.parametrize("filename", ["page.json", "files.json", "revisions/revisions.jsonl"])
def test_future_schema_versions_are_rejected(tmp_path, client, filename):
    writer = ArchiveWriter(tmp_path)
    writer.save_page(*collect_page(client, "test-page"))
    writer.save_page_files(123, [])
    writer.save_page_revisions(
        123,
        [
            (
                PageRevisionRecord(
                    page_id=123,
                    revision_id=1,
                    revision_no=0,
                    source=SourceRef(
                        path="revisions/sources/1.txt", sha256=sha256_text("old"), characters=3
                    ),
                ),
                "old",
            )
        ],
    )
    path = tmp_path / "pages/123" / filename
    record = json.loads(path.read_text(encoding="utf-8"))
    record["schema_version"] = 2
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid"):
        inspect_archive(tmp_path)
