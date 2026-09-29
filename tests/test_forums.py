"""Forum behavior using public AMC captures and isolated filesystem archives."""

import json
from datetime import UTC
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from wikidot_backup.cli import app
from wikidot_backup.collectors.forum_threads import collect_thread
from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.models.forum_records import ForumResumeRecord
from wikidot_backup.services.backup import backup_site
from wikidot_backup.services.backup_types import BackupOptions
from wikidot_backup.services.forum_backup import backup_forums
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.forum_archive import ForumState, read_records, read_thread, write_thread
from wikidot_backup.storage.inspection import inspect_archive
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.wikidot.errors import WikidotResourceError
from wikidot_backup.wikidot.forum_client import WikidotForumClient
from wikidot_backup.wikidot.models import WikidotSiteData

FIXTURES = Path(__file__).parent / "fixtures" / "forums"


def response(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def forum(*names):
    amc = Mock()
    amc.request.side_effect = [response(name) for name in names]
    return WikidotForumClient(amc)


def snapshot():
    return collect_thread(forum("thread", "posts"), 12031458, page_ids=[123], revisions=False)


def test_catalog_preserves_groups_and_category_counts():
    categories, groups, body = forum("start").catalog()
    assert len(categories) == 9
    assert len(groups) == 4
    assert next(c for c in categories if c.id == 2009297).reported_threads == 2017
    assert body == response("start")["body"]


def test_real_thread_reply_html_and_utc():
    thread, posts, _ = snapshot()
    assert thread.title == "SCP-009-UA-ARC - GOLD-картка"
    assert thread.category_id == 2009297
    assert thread.created_by.name == "Wikidot"
    assert thread.created_by.id is None
    assert posts[0].created_by.unix_name == "uther-mcclellan"
    assert posts[0].created_at.tzinfo == UTC
    assert int(posts[0].created_at.timestamp()) == 1585421396
    assert posts[1].parent_id == posts[0].post_id
    assert posts[0].title == ""
    assert "<blockquote>" in posts[0].html
    assert 'id="post-content-' not in posts[0].html
    assert posts[0].content_format == "html"
    assert thread.responses["posts-1"] == response("posts")["body"]


def test_post_pagination_follows_pager_not_number_of_posts():
    client = forum("thread-multiple", "posts-multiple-1", "posts-multiple-2")
    thread = client.thread(16762029)
    assert len(thread.posts) == 15
    assert sum(post.parent_id is None for post in thread.posts) == 12
    assert client.amc.request.call_args.kwargs["pageNo"] == "2"


def test_inner_html_keeps_nested_elements_and_whitespace():
    from bs4 import BeautifulSoup

    captured = response("posts")
    soup = BeautifulSoup(captured["body"], "html.parser")
    content = soup.select_one("#post-content-4569492")
    content.clear()
    content.append(BeautifulSoup(
        '\n<div class="example"><p>A&nbsp;<b>bold</b> <a href="/test">link</a></p>'
        '<br/><img src="/test.png"/></div>\n', "html.parser"
    ))
    expected = content.decode_contents()
    captured["body"] = str(soup)
    amc = Mock()
    amc.request.side_effect = [response("thread"), captured]

    thread = WikidotForumClient(amc).thread(12031458)

    assert thread.posts[0].html == expected
    assert thread.responses["posts-1"] == captured["body"]


def test_empty_thread_and_category_are_valid():
    assert forum("thread-empty", "posts-empty").thread(18342505).posts == []
    assert forum("category-empty").category_threads(2045113) == []


def test_revision_uses_content_not_body_and_preserves_html():
    client = forum("history", "revision", "revision")
    history = client.revisions(4569492)
    assert [r.revision_id for r in history] == [5482029, 5482054]
    assert [r.history_position for r in history] == [0, 1]
    assert history[-1].html == response("revision")["content"]
    assert history[-1].html != "ok"


def test_revision_wrong_post_rejected():
    with pytest.raises(RuntimeError, match="identity"):
        forum("unedited-history", "revision").revisions(4570884)


@pytest.mark.parametrize("body", ["", "<p>Temporary failure</p>"])
def test_invalid_catalog_is_not_empty_success(body):
    amc = Mock()
    amc.request.return_value = {"body": body}
    with pytest.raises(RuntimeError, match="Missing forum"):
        WikidotForumClient(amc).catalog()


def test_duplicate_posts_and_wrong_thread_fail():
    with pytest.raises(RuntimeError, match="identity"):
        forum("thread").thread(999)
    first, posts = response("thread"), response("posts")
    posts["body"] += posts["body"]
    amc = Mock()
    amc.request.side_effect = [first, posts]
    with pytest.raises(RuntimeError, match="Duplicate forum post"):
        WikidotForumClient(amc).thread(12031458)


def test_storage_retains_posts_absent_from_later_snapshot(tmp_path):
    thread, posts, history = snapshot()
    write_thread(tmp_path, thread, posts, history)
    thread.observed_post_ids = [posts[0].post_id]
    write_thread(tmp_path, thread, posts[:1], [])
    saved, retained, _ = read_thread(tmp_path, thread.thread_id)
    assert len(retained) == 2
    assert saved.observed_post_ids == [posts[0].post_id]
    info = inspect_archive(tmp_path)
    assert (info.forum_threads, info.forum_posts) == (1, 2)
    assert info.forums_bytes > 0


def test_storage_rejects_wrong_thread_id(tmp_path):
    thread, posts, history = snapshot()
    write_thread(tmp_path, thread, posts, history)
    path = tmp_path / "forums/threads/12031458/thread.json"
    thread.thread_id = 999
    path.write_text(thread.model_dump_json(), encoding="utf-8")
    with pytest.raises(RuntimeError, match="ownership"):
        read_thread(tmp_path, 12031458)


@pytest.mark.parametrize("line", ['{bad}', '{"thread_id":true,"revisions":false}',
                                 '{"thread_id":1,"revisions":"false"}'])
def test_corrupt_resume_rejected(tmp_path, line):
    path = tmp_path / ".state/forum-resume.jsonl"
    path.parent.mkdir()
    path.write_text(line, encoding="utf-8")
    with pytest.raises(ValueError):
        ForumState(tmp_path)


def service_client():
    client = Mock()
    client.site_data = WikidotSiteData(
        id=1398197, unix_name="scp-ukrainian", title="Example",
        domain="scp-ukrainian.wikidot.com", url="https://scp-ukrainian.wikidot.com",
    )
    categories, groups, body = forum("start").catalog()
    category = next(c for c in categories if c.id == 2009297)
    category.reported_threads = 1
    client.forums.catalog.return_value = ([category], groups, body)
    client.forums.category_threads.return_value = [12031458]
    client.forums.thread.return_value = forum("thread", "posts").thread(12031458)
    return client


def test_limited_resume_then_full_success_without_page_full_marker(tmp_path):
    client = service_client()
    first = backup_forums(client, tmp_path, limit=1)
    assert first.saved == 1
    assert ForumState(tmp_path).completed.keys() == {12031458}
    second = backup_forums(client, tmp_path)
    assert (second.saved, second.skipped) == (0, 1)
    assert client.forums.thread.call_count == 1
    assert not ForumState(tmp_path).path.exists()
    manifest = ArchiveManifestStore(tmp_path).load()
    assert manifest.last_successful_components == ["forums"]
    assert manifest.last_full_backup_at is None


def test_discovery_discrepancy_persists_and_preserves_resume(tmp_path):
    client = service_client()
    client.forums.catalog.return_value[0][0].reported_threads = 65
    result = backup_forums(client, tmp_path)
    assert result.saved == 1 and len(result.warnings) == 1
    assert ForumState(tmp_path).path.exists()
    assert ArchiveManifestStore(tmp_path).load().last_successful_run_at is None
    assert (tmp_path / "forums/catalog.json").is_file()
    assert list((tmp_path / "forums/runs").glob("*/catalog.json"))
    catalog = json.loads((tmp_path / "forums/catalog.json").read_text(encoding="utf-8"))
    run_directory = tmp_path / "forums/runs" / catalog["run_id"]
    report = json.loads((run_directory / "report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == catalog["run_id"]
    assert report["catalog"] == "catalog.json"


def test_post_count_mismatch_not_completed(tmp_path):
    client = service_client()
    client.forums.thread.return_value.reported_posts = 3
    result = backup_forums(client, tmp_path)
    assert result.saved == 1 and result.warnings
    assert not ForumState(tmp_path).completed
    assert read_thread(tmp_path, 12031458)[0].reported_posts == 3


def test_network_failure_retries_on_next_invocation(tmp_path):
    client = service_client()
    client.forums.thread.side_effect = WikidotResourceError("Unavailable")
    assert backup_forums(client, tmp_path).failed == 1
    assert not ForumState(tmp_path).completed
    client.forums.thread.side_effect = None
    assert backup_forums(client, tmp_path).saved == 1


def test_programming_error_propagates(tmp_path):
    client = service_client()
    client.forums.thread.side_effect = ValueError("Invalid schema")
    with pytest.raises(ValueError, match="Invalid schema"):
        backup_forums(client, tmp_path)


def test_refresh_fetches_completed_threads(tmp_path):
    client = service_client()
    backup_forums(client, tmp_path, limit=1)
    backup_forums(client, tmp_path, limit=1, refresh=True)
    assert client.forums.thread.call_count == 2


def test_adding_revisions_refetches_and_failed_history_does_not_complete(tmp_path):
    client = service_client()
    backup_forums(client, tmp_path, limit=1)
    client.forums.revisions.side_effect = WikidotResourceError("Unavailable history")
    result = backup_forums(client, tmp_path, revisions=True)
    assert result.failed == 1
    state = read_records(ForumState(tmp_path).path, ForumResumeRecord)
    assert not state[0].revisions
    assert not read_thread(tmp_path, 12031458)[0].revisions_included


def test_cli_coverage_exit_and_close(tmp_path, monkeypatch):
    client = service_client()
    client.forums.catalog.return_value[0][0].reported_threads = 65
    monkeypatch.setattr("wikidot_backup.cli.WikidotClient", lambda _: client)
    result = CliRunner().invoke(app, ["backup-forums", "scp-ukrainian", "-o", str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert "Coverage warning" in result.output
    client.close.assert_called_once()


def test_page_discussions_share_thread_storage(tmp_path, client, page_data):
    data = page_data()
    data.discussion_thread_id = 12031458
    client.fetch_page.return_value = data
    ArchiveWriter(tmp_path).save_page(*collect_page(client, "test-page"))
    remote = service_client()
    remote.forums.category_threads.return_value = []
    remote.forums.catalog.return_value[0][0].reported_threads = 0
    backup_forums(remote, tmp_path)
    assert read_thread(tmp_path, 12031458)[0].archived_page_ids == [123]
    remote.forums.thread.assert_called_once_with(12031458)


def test_thread_publication_failure_rolls_back(tmp_path, monkeypatch):
    thread, posts, history = snapshot()
    write_thread(tmp_path, thread, posts, history)
    directory = tmp_path / "forums/threads/12031458"
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    thread.title = "Changed"
    original = Path.replace

    def fail(path, target):
        if path.suffix == ".new" and Path(target).name == "posts.jsonl":
            raise OSError("Simulated failure")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="Simulated failure"):
        write_thread(tmp_path, thread, posts, history)
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_category_empty_trailing_page_is_fetched():
    first = response("category")
    # Retain the real rows, but use a bounded two-page pager for the fixture.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(first["body"], "html.parser")
    for pager in soup.select(".pager"):
        pager.clear()
        pager.append(BeautifulSoup(
            '<span class="current">1</span><a href="/p/2">2</a>', "html.parser"
        ))
    first["body"] = str(soup)
    last = response("category-empty")
    last["body"] += '<div class="pager"><a href="/p/1">1</a><span class="current">2</span></div>'
    amc = Mock()
    amc.request.side_effect = [first, last]
    ids = WikidotForumClient(amc).category_threads(2009297)
    assert len(ids) == 20
    assert amc.request.call_args.kwargs["p"] == "2"


def test_successful_revision_archive_and_history_retained(tmp_path):
    remote = service_client()
    versions = forum("history", "revision", "revision").revisions(4569492)
    reply = forum("thread", "posts").thread(12031458).posts[1]
    reply.revision_id, reply.history_position = 5483816, 0
    remote.forums.revisions.side_effect = [versions, [reply]]
    backup_forums(remote, tmp_path, revisions=True)
    thread, _, history = read_thread(tmp_path, 12031458)
    assert thread.revisions_included and len(history) == 3
    backup_forums(remote, tmp_path)
    thread, _, history = read_thread(tmp_path, 12031458)
    assert not thread.revisions_included and len(history) == 3
    assert inspect_archive(tmp_path).forum_revisions == 3


@pytest.mark.parametrize("problem", [None, "coverage", "network", "page"])
def test_combined_backup_finalizes_only_after_both_phases(client, tmp_path, problem):
    client.forums = service_client().forums
    if problem == "coverage":
        client.forums.catalog.return_value[0][0].reported_threads = 65
    elif problem == "network":
        client.forums.thread.side_effect = WikidotResourceError("Forum unavailable")
    elif problem == "page":
        client.fetch_page.side_effect = WikidotResourceError("Page unavailable")

    result = backup_site(client, tmp_path, options=BackupOptions(include_forums=True))
    manifest = ArchiveManifestStore(tmp_path).load()

    assert result.forums is not None
    assert result.resume_state_cleared == (problem is None)
    assert (manifest.last_full_backup_at is not None) == (problem is None)
    if problem is None:
        assert "forums" in manifest.last_successful_components
        assert "page" in manifest.last_successful_components
        assert not ForumState(tmp_path).path.exists()
    elif problem in {"coverage", "network"}:
        assert (tmp_path / ".state/resume.jsonl").exists()
    else:
        assert ForumState(tmp_path).completed


def test_combined_limit_retains_both_resume_files(client, tmp_path):
    client.forums = service_client().forums
    result = backup_site(
        client, tmp_path, options=BackupOptions(include_forums=True), limit=1,
    )
    assert result.forums.saved == 1
    assert not result.resume_state_cleared
    assert ForumState(tmp_path).path.exists()
    assert (tmp_path / ".state/resume.jsonl").exists()
    assert ArchiveManifestStore(tmp_path).load().last_full_backup_at is None


@pytest.mark.parametrize("failure", [False, True])
def test_forum_progress_finishes_attempts_and_excludes_resumed_threads(tmp_path, failure):
    client = service_client()
    if failure:
        client.forums.thread.side_effect = WikidotResourceError("Unavailable")
    events = []
    result = backup_forums(client, tmp_path, limit=1, report=events.append)
    thread_events = [event for event in events if event.phase == "threads"]
    assert thread_events[0].completed == 0 and thread_events[0].total == 1
    assert thread_events[-1].completed == 1
    assert thread_events[-1].saved == result.saved
    assert thread_events[-1].failed == result.failed

    if not failure:
        events.clear()
        backup_forums(client, tmp_path, limit=1, report=events.append)
        thread_events = [event for event in events if event.phase == "threads"]
        assert len(thread_events) == 1 and thread_events[0].total == 0
