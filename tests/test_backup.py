from unittest.mock import Mock

import httpx
import pytest

from wikidot_backup.services.backup import backup_site
from wikidot_backup.services.backup_types import BackupComponent, BackupOptions
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.storage.state import BackupState
from wikidot_backup.wikidot.errors import WikidotResourceError


def test_default_backup_requires_page_and_files() -> None:
    options = BackupOptions()

    assert options.required_components == {
        BackupComponent.PAGE,
        BackupComponent.FILES,
    }


def test_revision_backup_adds_revisions() -> None:
    options = BackupOptions(include_revisions=True)

    assert options.required_components == {
        BackupComponent.PAGE,
        BackupComponent.FILES,
        BackupComponent.REVISIONS,
    }


def test_no_files_removes_file_component() -> None:
    options = BackupOptions(include_files=False)

    assert options.required_components == {
        BackupComponent.PAGE,
    }


def test_limited_run_keeps_state_even_when_all_pages_processed(client, tmp_path):
    result = backup_site(client, tmp_path, options=BackupOptions(), limit=20)
    assert result.saved == 1 and result.limited
    assert not result.resume_state_cleared
    manifest = ArchiveManifestStore(tmp_path).load()
    assert manifest.last_successful_run_at is not None
    assert manifest.last_full_backup_at is None
    assert BackupState(tmp_path).load_page_states()["test-page"].completed_components == {
        BackupComponent.PAGE,
        BackupComponent.FILES,
    }


def test_unlimited_resume_finalizes_without_recollecting(client, tmp_path):
    backup_site(client, tmp_path, options=BackupOptions(), limit=20)
    client.reset_mock()
    result = backup_site(client, tmp_path, options=BackupOptions())
    assert result.already_completed == 1
    assert result.saved == 0 and result.resume_state_cleared
    client.fetch_page.assert_not_called()
    client.validate_page_identity.assert_called_once_with("test-page", 123)
    assert ArchiveManifestStore(tmp_path).load().last_full_backup_at is not None
    assert not (tmp_path / ".state/resume.jsonl").exists()


def test_component_failure_retries_only_unfinished_component(client, tmp_path):
    client.fetch_page_files.side_effect = httpx.ReadTimeout("offline")
    progress = Mock()
    result = backup_site(client, tmp_path, options=BackupOptions(), progress=progress)
    assert result.failed == result.processed == 1
    progress.page_failed.assert_called_once()
    progress.page_succeeded.assert_not_called()
    assert BackupState(tmp_path).load_page_states()["test-page"].completed_components == {
        BackupComponent.PAGE
    }
    assert ArchiveManifestStore(tmp_path).load().last_successful_run_at is None
    client.fetch_page_files.side_effect = None
    client.fetch_page.reset_mock()
    result = backup_site(client, tmp_path, options=BackupOptions())
    assert result.saved == 1 and result.resume_state_cleared
    client.fetch_page.assert_not_called()


@pytest.mark.parametrize("error", [TypeError("bug"), ValueError("schema"), OSError("disk")])
def test_unexpected_errors_abort_instead_of_becoming_page_failures(client, tmp_path, error):
    client.fetch_page.side_effect = error
    with pytest.raises(type(error), match=str(error)):
        backup_site(client, tmp_path, options=BackupOptions())
    assert ArchiveManifestStore(tmp_path).load().last_successful_run_at is None
    assert not (tmp_path / ".state/resume.jsonl").exists()


def test_discovery_failure_does_not_record_success(client, tmp_path):
    client.list_page_fullnames.side_effect = RuntimeError("Invalid ListPages")
    with pytest.raises(RuntimeError, match="ListPages"):
        backup_site(client, tmp_path, options=BackupOptions())
    client.fetch_page.assert_not_called()
    assert ArchiveManifestStore(tmp_path).load().last_full_backup_at is None


def test_completed_resume_does_not_hide_replacement_page(client, tmp_path):
    backup_site(client, tmp_path, options=BackupOptions(), limit=1)
    client.validate_page_identity.side_effect = WikidotResourceError("identity changed")
    with pytest.raises(WikidotResourceError, match="identity changed"):
        backup_site(client, tmp_path, options=BackupOptions())
    assert (tmp_path / ".state/resume.jsonl").is_file()
    assert ArchiveManifestStore(tmp_path).load().last_full_backup_at is None


def test_revision_failure_never_completes_component(client, tmp_path):
    client.fetch_page_revisions.side_effect = httpx.ReadTimeout("offline")
    result = backup_site(client, tmp_path, options=BackupOptions(include_revisions=True))
    assert result.failed == 1
    assert (
        BackupComponent.REVISIONS
        not in BackupState(tmp_path).load_page_states()["test-page"].completed_components
    )


def test_page_write_failure_never_completes_component(client, tmp_path, monkeypatch):
    from wikidot_backup.storage.archive import ArchiveWriter

    monkeypatch.setattr(ArchiveWriter, "save_page", Mock(side_effect=OSError("disk")))
    with pytest.raises(OSError):
        backup_site(client, tmp_path, options=BackupOptions())
    assert not BackupState(tmp_path).load_page_states()
