"""Exercise endpoint wiring, identity checks, pagination and retry boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from tenacity import wait_none

from wikidot_backup.config import WIKIDOT_RETRY_ATTEMPTS
from wikidot_backup.wikidot.amc import WikidotAmcClient
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.errors import WikidotResourceError


@pytest.fixture
def raw_client():
    client = object.__new__(WikidotClient)
    client._amc = Mock()
    client._site = Mock()
    return client


def test_revision_endpoint_preserves_real_leading_tab(raw_client):
    raw_client._amc.request.return_value = {"body": '<div class="page-source">\ttext<br></div>'}
    assert raw_client.fetch_revision_source(42) == "\ttext\n"
    raw_client._amc.request.assert_called_once_with("history/PageSourceModule", revision_id="42")


def test_current_endpoint_removes_only_transport_tab(raw_client):
    raw_client._amc.request.return_value = {"body": '<div class="page-source">\t\ttext<br></div>'}
    assert raw_client.fetch_current_source(42) == "\ttext\n"
    raw_client._amc.request.assert_called_once_with("viewsource/ViewSourceModule", page_id="42")


def test_discovery_paginates_with_offsets(raw_client):
    first = "\n".join(f"page-{i:03}" for i in range(250))
    raw_client._amc.request.side_effect = [
        {"body": f'<div class="list-pages-box">{first}</div>'},
        {"body": '<div class="list-pages-box">last<div class="pager">1 2 next</div></div>'},
    ]
    counts = []
    assert len(raw_client.list_page_fullnames(report=counts.append)) == 251
    assert counts == [250, 251]
    requests = raw_client._amc.request.call_args_list
    assert [call.kwargs["offset"] for call in requests] == ["0", "250"]
    assert all(
        call.kwargs["order"] == "fullname" and call.kwargs["limit"] == "250" for call in requests
    )


def test_discovery_rejects_unexpected_html():
    with pytest.raises(RuntimeError, match="ListPages"):
        WikidotClient._parse_list_pages_response("<div>unexpected</div>")
    assert WikidotClient._parse_list_pages_response('<div class="list-pages-box"></div>') == []


def test_discovery_rejects_ignored_offset(raw_client):
    body = "\n".join(f"page-{i}" for i in range(250))
    raw_client._amc.request.return_value = {"body": f'<div class="list-pages-box">{body}</div>'}
    with pytest.raises(RuntimeError, match="no new pages"):
        raw_client.list_page_fullnames()


@pytest.mark.parametrize("method", ["fetch_page_files", "fetch_page_revisions"])
def test_component_fetch_rejects_replacement_page(raw_client, method):
    raw_client._site.page.get.return_value = SimpleNamespace(id=999, fullname="test-page")
    with pytest.raises(WikidotResourceError, match="identity changed"):
        getattr(raw_client, method)("test-page", expected_page_id=123)


def test_source_failure_has_one_retry_budget(raw_client, monkeypatch):
    raw_client._site.page.get.return_value = SimpleNamespace(id=123, fullname="test-page")
    amc = object.__new__(WikidotAmcClient)
    amc.base_url = "https://example.test"
    amc._http = Mock()
    amc._http.post.side_effect = httpx.ReadTimeout("offline")
    raw_client._amc = amc
    monkeypatch.setattr(WikidotAmcClient.request.retry, "wait", wait_none())
    with pytest.raises(httpx.ReadTimeout):
        raw_client.fetch_page("test-page")
    assert amc._http.post.call_count == WIKIDOT_RETRY_ATTEMPTS
    assert raw_client._site.page.get.call_count == 1


def test_metadata_lookup_retries_independently(raw_client, monkeypatch):
    page = SimpleNamespace(id=123, fullname="test-page")
    raw_client._site.page.get.side_effect = [httpx.ReadTimeout("offline"), page]
    monkeypatch.setattr(WikidotClient._get_page.retry, "wait", wait_none())
    raw_client.validate_page_identity("test-page", 123)
    assert raw_client._site.page.get.call_count == 2


def test_lazy_discussion_lookup_retries_independently(raw_client, monkeypatch):
    from unittest.mock import PropertyMock
    page = Mock()
    discussion = PropertyMock(side_effect=[httpx.ReadTimeout("offline"), None])
    type(page).discussion = discussion
    monkeypatch.setattr(WikidotClient._get_discussion.retry, "wait", wait_none())
    assert raw_client._get_discussion(page) is None
    assert discussion.call_count == 2
