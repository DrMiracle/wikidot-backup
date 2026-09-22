"""Small realistic data factories for integration-boundary and service tests."""
from unittest.mock import Mock

import pytest

from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.models import WikidotPageData, WikidotSiteData


@pytest.fixture
def page_data():
    """Build normalized page data without contacting Wikidot."""

    def make(fullname="test-page", page_id=123, source="source\n", latest_revision_no=0):
        return WikidotPageData(
            page_id=page_id,
            fullname=fullname,
            name=fullname,
            category="_default",
            title=None,
            parent_fullname=None,
            tags=[],
            hidden_tags=[],
            children_count=0,
            comments_count=0,
            size=len(source),
            rating=None,
            votes_count=None,
            rating_percent=None,
            latest_revision_no=latest_revision_no,
            created_by=None,
            created_at=None,
            updated_by=None,
            updated_at=None,
            commented_by=None,
            commented_at=None,
            discussion_thread_id=None,
            metas={},
            source=source,
        )

    return make


@pytest.fixture
def client(page_data):
    """Provide an offline client with one page and no optional content."""
    result = Mock(spec=WikidotClient)
    result.site_data = WikidotSiteData(
        1, "example", None, "example.wikidot.com", "https://example.wikidot.com"
    )
    result.list_page_fullnames.return_value = ["test-page"]
    result.fetch_page.return_value = page_data()
    result.fetch_page_files.return_value = []
    result.fetch_page_revisions.return_value = []
    return result
