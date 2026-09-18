from wikidot_backup.services.estimate import BackupEstimate


def test_estimated_total_includes_all_selected_content() -> None:
    estimate = BackupEstimate(
        pages=10,
        current_source_bytes=100,
        attachment_records=2,
        attachment_reported_bytes=200,
        attachments_with_unknown_size=0,
        revision_records=5,
        revision_source_estimated_bytes=300,
    )

    assert estimate.estimated_total_bytes == 600
