"""Offline export contracts, including incomplete archives and hostile filenames."""

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

import pytest
from bs4 import BeautifulSoup
from typer.testing import CliRunner

from wikidot_backup.cli import app
from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.models.common import BlobRef, SourceRef, UserRef
from wikidot_backup.models.file import PageFileRecord
from wikidot_backup.models.forum_records import ForumPostRecord, ForumThreadRecord
from wikidot_backup.models.manifest import ArchiveSite
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.services.export import export_archive
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.forum_archive import write_thread
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.ui.export_html import render_post_html, source_html
from wikidot_backup.util.export_names import export_name
from wikidot_backup.util.hashing import sha256_text


def make_archive(root, client, page_data, *, fullname="test-page", thread_id=None):
    ArchiveManifestStore(root).ensure_archive(
        ArchiveSite(
            id=1,
            unix_name="example",
            domain="example.wikidot.com",
            url="https://example.wikidot.com",
        )
    )
    data = page_data(fullname=fullname)
    data.discussion_thread_id = thread_id
    client.fetch_page.return_value = data
    writer = ArchiveWriter(root)
    writer.save_page(*collect_page(client, fullname))
    writer.save_page_files(123, [])
    return writer


def add_thread(root, thread_id=12, *, linked=True):
    user = UserRef(id=1, name="<Author>", unix_name="author")
    posts = [
        ForumPostRecord(
            thread_id=thread_id,
            post_id=identifier,
            parent_id=1 if identifier == 2 else None,
            title="",
            html="<p>Hello <b>world</b></p>",
            created_at=datetime.now(UTC),
            created_by=user,
        )
        for identifier in (1, 2, 3)
    ]
    thread = ForumThreadRecord(
        thread_id=thread_id,
        category_id=None,
        title="",
        created_at=datetime.now(UTC),
        created_by=user,
        fetched_at=datetime.now(UTC),
        reported_posts=2,
        observed_post_ids=[1, 2],
        archived_page_ids=[123] if linked else [],
        revisions_included=False,
        responses={},
    )
    write_thread(root, thread, posts, [])


def fingerprints(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_readable_export_preserves_bytes_links_and_archive(tmp_path, client, page_data):
    root, output = tmp_path / "backup", tmp_path / "readable"
    writer = make_archive(root, client, page_data, fullname="scp:test", thread_id=12)
    attachment_bytes = b"\xff\xd8original\x00\r\n"
    checksum = hashlib.sha256(attachment_bytes).hexdigest()
    attachments = [
        PageFileRecord(
            page_id=123,
            file_id=identifier,
            name=name,
            source_url="https://example.com/image.jpg",
            content=BlobRef(
                path=f"blobs/sha256/{checksum}", sha256=checksum, size=len(attachment_bytes)
            ),
        )
        for identifier, name in [(1, "photo.jpg"), (2, "PHOTO.jpg"), (3, "../CON.jpg")]
    ]
    writer.save_page_files(123, [(attachment, attachment_bytes) for attachment in attachments])
    revision_source = "\told\n\n"
    revision = PageRevisionRecord(
        page_id=123,
        revision_id=5,
        revision_no=0,
        source=SourceRef(
            path="revisions/sources/5.txt",
            sha256=sha256_text(revision_source),
            characters=len(revision_source),
        ),
    )
    writer.save_page_revisions(123, [(revision, revision_source)])
    add_thread(root)
    add_thread(root, 13, linked=False)
    before = fingerprints(root)

    result = export_archive(root, output)

    assert result["status"] == "completed"
    page_dir = output / result["pages"][0]["path"]
    assert page_dir.name == "scp_test"
    assert (page_dir / "source.txt").read_bytes() == b"source\n"
    files = json.loads((page_dir / "files.json").read_text())["attachments"]
    assert len({record["path"].casefold() for record in files}) == 3
    for record in files:
        assert (page_dir / record["path"]).read_bytes() == attachment_bytes
    exported_revision = json.loads((page_dir / "revisions/revisions.jsonl").read_text())
    assert (page_dir / exported_revision["source"]["path"]).read_bytes() == revision_source.encode()
    html = (page_dir / "discussion/index.html").read_text()
    assert "&lt;Author&gt;" in html and 'href="#post-1"' in html
    assert "Retained posts absent" in html
    assert len(result["standalone_threads"]) == 1
    assert fingerprints(root) == before
    # All generated local navigation links resolve, including discussion back links.
    for path in output.rglob("*.html"):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for anchor in soup.select("a[href]"):
            url = urlsplit(anchor["href"])
            if not url.scheme and url.path:
                assert (path.parent / unquote(url.path)).exists(), (path, anchor["href"])


def test_missing_files_and_discussion_are_reported(tmp_path, client, page_data):
    root, output = tmp_path / "backup", tmp_path / "readable"
    make_archive(root, client, page_data, thread_id=12)
    (root / "pages/123/files.json").unlink()
    result = export_archive(root, output)
    assert result["status"] == "completed_with_warnings"
    assert result["warning_count"] == 2
    assert "filenames and missing count unknown" in result["pages"][0]["warnings"][0]
    assert "Discussion thread 12" in result["pages"][0]["warnings"][1]


def test_missing_blob_is_warning_corrupt_blob_is_failure(tmp_path, client, page_data):
    root = tmp_path / "backup"
    writer = make_archive(root, client, page_data)
    data = b"image"
    digest = hashlib.sha256(data).hexdigest()
    record = PageFileRecord(
        page_id=123,
        file_id=1,
        name="image.png",
        source_url="https://example.com",
        content=BlobRef(path=f"blobs/sha256/{digest}", sha256=digest, size=5),
    )
    writer.save_page_files(123, [(record, data)])
    blob = root / record.content.path
    blob.unlink()
    assert export_archive(root, tmp_path / "missing")["warning_count"] == 1
    blob.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="integrity"):
        export_archive(root, tmp_path / "corrupt")
    assert json.loads((tmp_path / "corrupt/export.json").read_text())["status"] == "incomplete"


def test_output_must_be_new_and_separate(tmp_path, client, page_data):
    root = tmp_path / "backup"
    make_archive(root, client, page_data)
    for output in (root, root / "export", tmp_path):
        with pytest.raises(ValueError, match="overlap"):
            export_archive(root, output)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        export_archive(root, existing)


def test_source_path_escape_rejected(tmp_path, client, page_data):
    root = tmp_path / "backup"
    make_archive(root, client, page_data)
    metadata = root / "pages/123/page.json"
    data = json.loads(metadata.read_text())
    data["source"]["path"] = "../../secret.txt"
    metadata.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid archive-relative"):
        export_archive(root, tmp_path / "export")


def test_legacy_revision_order_is_sorted_without_rewriting_archive(tmp_path, client, page_data):
    root = tmp_path / "backup"
    make_archive(root, client, page_data)
    revisions_dir = root / "pages/123/revisions"
    (revisions_dir / "sources").mkdir(parents=True)
    records = []
    for number in (2, 1, 0):
        source = f"revision {number}\n"
        relative = f"revisions/sources/{number + 10}.txt"
        (root / "pages/123" / relative).write_bytes(source.encode())
        records.append(
            PageRevisionRecord(
                page_id=123,
                revision_id=number + 10,
                revision_no=number,
                source=SourceRef(path=relative, sha256=sha256_text(source), characters=len(source)),
            ).model_dump_json()
        )
    original = "\n".join(records) + "\n"
    (revisions_dir / "revisions.jsonl").write_bytes(original.encode())
    output = tmp_path / "export"
    export_archive(root, output)
    exported = (output / "pages/test-page/revisions/revisions.jsonl").read_text().splitlines()
    assert [json.loads(line)["revision_no"] for line in exported] == [0, 1, 2]
    assert (revisions_dir / "revisions.jsonl").read_bytes() == original.encode()


def test_pending_transaction_rejected_before_creating_export(tmp_path, client, page_data):
    root = tmp_path / "backup"
    make_archive(root, client, page_data)
    transaction = root / ".state/transactions/interrupted/transaction.json"
    transaction.parent.mkdir(parents=True)
    transaction.write_text("{}")
    output = tmp_path / "export"
    with pytest.raises(RuntimeError, match="Interrupted archive write"):
        export_archive(root, output)
    assert not output.exists()


def test_sanitized_view_does_not_execute_or_auto_load_remote_content():
    content = (
        '<script>alert(1)</script><p onclick="bad()">Text <b>bold</b></p>'
        '<a href="javascript:bad()">bad</a><a href="/page">good</a>'
        '<img src="https://example.com/a.png" onerror="bad()">'
        '<iframe src="https://example.com"></iframe><svg onload="bad()"></svg>'
    )
    html = render_post_html(content, "https://example.wikidot.com")
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.select("script, iframe, img, svg, [onclick], [onerror], [onload]")
    assert "javascript:" not in html and "<b>bold</b>" in html
    assert 'href="https://example.wikidot.com/page"' in html


def test_source_view_preserves_unicode_whitespace_and_escapes_markup():
    source = '\n\tЗагальні відомості\n\n<script>alert("test")</script>\n'
    html = source_html(source, title="Source", text_path="source.txt", back_path="index.html")
    soup = BeautifulSoup(html.decode("utf-8"), "html.parser")
    assert soup.select_one("meta[charset]")["charset"] == "utf-8"
    assert soup.pre.get_text() == source
    assert not soup.select("script")
    assert "<pre><span></span>\n" in html.decode("utf-8")


def test_export_links_to_utf8_source_viewers(tmp_path, client, page_data):
    root = tmp_path / "backup"
    writer = make_archive(root, client, page_data)
    source = "\nЗагальні відомості\n"
    client.fetch_page.return_value = page_data(source=source)
    writer.save_page(*collect_page(client, "test-page"))
    revision = PageRevisionRecord(
        page_id=123,
        revision_id=10,
        revision_no=0,
        source=SourceRef(
            path="revisions/sources/10.txt", sha256=sha256_text(source), characters=len(source)
        ),
    )
    writer.save_page_revisions(123, [(revision, source)])
    output = tmp_path / "export"
    export_archive(root, output)
    page = output / "pages/test-page"
    assert (page / "source.txt").read_bytes() == source.encode("utf-8")
    assert 'href="source.html"' in (page / "index.html").read_text(encoding="utf-8")
    assert 'href="sources/00000-10.html"' in (page / "revisions/index.html").read_text()
    for path in (page / "source.html", page / "revisions/sources/00000-10.html"):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        assert soup.pre.get_text() == source


@pytest.mark.parametrize("name", ["CON", "nul.txt", "COM1.jpg", "..", "a/b", "a:b?", "a. "])
def test_portable_names(name):
    used = set()
    first = export_name(name, identifier=1, used=used)
    second = export_name(name.upper(), identifier=2, used=used)
    assert first.casefold() != second.casefold()
    assert not any(character in first for character in '<>:"/\\|?*')
    assert not first.endswith((".", " "))


def test_cli_export_warning_exit(tmp_path, client, page_data):
    root = tmp_path / "backup"
    make_archive(root, client, page_data)
    (root / "pages/123/files.json").unlink()
    result = CliRunner().invoke(app, ["export", str(root), "-o", str(tmp_path / "readable")])
    assert result.exit_code == 2, result.output
    assert "1 warning" in result.output
