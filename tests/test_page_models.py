from wikidot_backup.models.common import SourceRef
from wikidot_backup.models.page import PageRecord


def test_page_record_allows_missing_title() -> None:
    """Pages without explicit Wikidot titles must remain archivable."""

    page = PageRecord(
        page_id=123,
        fullname="fragment:test",
        name="test",
        category="fragment",
        title=None,
        children_count=0,
        comments_count=0,
        size=0,
        source=SourceRef(
            path="test_path",
            sha256="0" * 64,
            characters=0,
        ),
    )

    assert page.title is None