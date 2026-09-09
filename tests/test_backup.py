from wikidot_backup.services.backup_types import BackupOptions, BackupComponent


def test_default_backup_requires_page_and_files() -> None:
    options = BackupOptions()

    assert options.required_components == {
        BackupComponent.PAGE,
        BackupComponent.FILES,
    }


def test_revision_backup_adds_revisions() -> None:
    options = BackupOptions(
        include_revisions=True
    )

    assert options.required_components == {
        BackupComponent.PAGE,
        BackupComponent.FILES,
        BackupComponent.REVISIONS,
    }


def test_no_files_removes_file_component() -> None:
    options = BackupOptions(
        include_files=False
    )

    assert options.required_components == {
        BackupComponent.PAGE,
    }
