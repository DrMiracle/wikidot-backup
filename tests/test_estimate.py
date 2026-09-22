from wikidot_backup.services.backup_types import BackupOptions
from wikidot_backup.services.estimate import BackupEstimate, estimate_backup
from wikidot_backup.wikidot.models import WikidotFileData


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


def test_estimate_measures_utf8_and_reports_unknowns(client, page_data):
    client.list_page_fullnames.return_value = ["first", "second"]
    client.fetch_page.side_effect = [
        page_data("first", source="я", latest_revision_no=2),
        page_data("second", source="abc", latest_revision_no=None),
    ]
    client.fetch_page_files.side_effect = [
        [WikidotFileData(1, "one", "https://example.test/one", None, 20)],
        [WikidotFileData(2, "two", "https://example.test/two", None, None)],
    ]
    result = estimate_backup(client, options=BackupOptions(include_revisions=True))
    assert result.current_source_bytes == 5
    assert result.attachment_records == 2
    assert result.attachment_reported_bytes == 20
    assert result.attachments_with_unknown_size == 1
    assert result.revision_records == 3
    assert result.revision_source_estimated_bytes == 6
    assert result.pages_with_unknown_revision_count == 1
    client.fetch_file_content.assert_not_called()
    client.fetch_page_revisions.assert_not_called()


def test_estimate_limit_and_disabled_components(client):
    client.list_page_fullnames.return_value = ["test-page", "second"]
    result = estimate_backup(client, options=BackupOptions(include_files=False), limit=1)
    assert result.pages == 1
    assert result.revision_records == result.attachment_records == 0
    client.fetch_page_files.assert_not_called()
    assert client.fetch_page.call_count == 1
