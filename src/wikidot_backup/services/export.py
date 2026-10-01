"""Offline readable export of canonical pages, attachments, and discussions."""

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from pathlib import Path

from wikidot_backup.models.file import PageFilesRecord
from wikidot_backup.models.page import PageRecord
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.storage.atomic import archive_path, atomic_write, require_settled_archive
from wikidot_backup.storage.forum_archive import json_lines, read_catalog, read_records, read_thread
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.ui.export_html import discussion_html, document, link, source_html
from wikidot_backup.util.export_names import export_name


def _write_json(path: Path, value: dict) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _copy_checked(
    source: Path,
    destination: Path,
    checksum: str,
    warnings: list[str],
    label: str,
    *,
    size: int | None = None,
) -> bool:
    """Copy original bytes only after checking their archived integrity metadata."""
    if not source.is_file():
        warnings.append(f"{label}: archived content is missing.")
        return False
    digest = sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != checksum or (size is not None and source.stat().st_size != size):
        raise ValueError(f"Archive integrity check failed: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return True


def _export_files(
    root: Path, page_dir: Path, target: Path, page_id: int, warnings: list[str]
) -> list[str]:
    """Materialize known attachment names; never infer names from orphaned blobs."""
    metadata_path = archive_path(page_dir, "files.json")
    if not metadata_path.exists():
        warnings.append(
            "Attachment collection was not archived; filenames and missing count unknown."
        )
        return []
    collection = PageFilesRecord.model_validate_json(metadata_path.read_bytes())
    if collection.page_id != page_id or any(
        record.page_id != page_id for record in collection.files
    ):
        raise ValueError(f"Attachment ownership mismatch: {metadata_path}")
    if len({record.file_id for record in collection.files}) != len(collection.files):
        raise ValueError(f"Duplicate attachment IDs: {metadata_path}")

    used_names: set[str] = set()
    mappings = []
    links = []
    for record in sorted(collection.files, key=lambda record: record.file_id):
        filename = export_name(record.name, identifier=record.file_id, used=used_names)
        relative = f"files/{filename}"
        copied = False
        if record.content is not None:
            copied = _copy_checked(
                archive_path(root, record.content.path),
                target / relative,
                record.content.sha256,
                warnings,
                f"Attachment {record.name}",
                size=record.content.size,
            )
        else:
            warnings.append(
                f"Attachment {record.name}: {record.retrieval_error or 'no archived bytes'}"
            )
        mappings.append(
            {
                "original_name": record.name,
                "path": relative if copied else None,
                "status": "copied" if copied else "missing",
                "archive_metadata": record.model_dump(mode="json"),
            }
        )
        if copied:
            links.append(link(relative, record.name))
    _write_json(
        target / "files.json",
        {
            "export_schema_version": 1,
            "page_id": page_id,
            "attachments": mappings,
        },
    )
    return links


def _export_revisions(page_dir: Path, target: Path, page_id: int, warnings: list[str]) -> int:
    """Order both legacy and current histories by revision number for browsing."""
    path = archive_path(page_dir, "revisions/revisions.jsonl")
    if not path.exists():
        return 0
    revisions = read_records(path, PageRevisionRecord)
    if any(revision.page_id != page_id for revision in revisions):
        raise ValueError(f"Revision ownership mismatch: {path}")
    if len({revision.revision_id for revision in revisions}) != len(revisions) or len(
        {revision.revision_no for revision in revisions}
    ) != len(revisions):
        raise ValueError(f"Duplicate revision records: {path}")
    exported_records = []
    items = []
    for revision in sorted(revisions, key=lambda revision: revision.revision_no):
        relative = f"revisions/sources/{revision.revision_no:05}-{revision.revision_id}.txt"
        copied = _copy_checked(
            archive_path(page_dir, revision.source.path),
            target / relative,
            revision.source.sha256,
            warnings,
            f"Revision {revision.revision_no}",
        )
        exported = revision.model_copy(deep=True)
        exported.source.path = relative
        exported_records.append(exported)
        label = f"Revision {revision.revision_no} — {revision.comment or '(no comment)'}"
        if copied:
            text_path = target / relative
            atomic_write(
                text_path.with_suffix(".html"),
                source_html(
                    text_path.read_bytes().decode("utf-8"),
                    title=label,
                    text_path=text_path.name,
                    back_path="../index.html",
                ),
            )
        items.append(
            link(relative.removeprefix("revisions/").removesuffix(".txt") + ".html", label)
            if copied
            else escape(label + " [source missing]")
        )
    atomic_write(target / "revisions/revisions.jsonl", json_lines(exported_records))
    atomic_write(
        target / "revisions/index.html",
        document(
            "Page revision history",
            "<p>"
            + link("../index.html", "Back to page")
            + "</p><ul>"
            + "".join(f"<li>{item}</li>" for item in items)
            + "</ul>",
        ),
    )
    return len(revisions)


def _export_discussion(
    root: Path, thread_id: int, target: Path, site_url: str, warnings: list[str], *, back_path: str
) -> str:
    """Preserve all records and render a basic, non-executable discussion view."""
    archive_path(root, f"forums/threads/{thread_id}")
    thread, posts, history = read_thread(root, thread_id)
    parents = {post.post_id: post.parent_id for post in posts}
    for post in posts:
        current = post.post_id
        visited = set()
        while current is not None:
            if current in visited or current not in parents:
                raise ValueError(f"Broken reply relationship in thread {thread_id}")
            visited.add(current)
            current = parents[current]
    if thread.reported_posts != len(thread.observed_post_ids):
        warnings.append(f"Thread {thread_id}: reported post count differs from observed posts.")
    atomic_write(target / "thread.json", thread.model_dump_json(indent=2).encode("utf-8"))
    atomic_write(target / "posts.jsonl", json_lines(posts))
    if history or thread.revisions_included:
        atomic_write(target / "post-revisions.jsonl", json_lines(history))
    atomic_write(
        target / "index.html", discussion_html(thread, posts, site_url, back_path=back_path)
    )
    return thread.title or f"Untitled thread {thread_id}"


def export_archive(
    root: Path, output: Path, *, report: Callable[[str], None] | None = None
) -> dict:
    """Export to a new, separate directory. Failure leaves an explicitly incomplete export."""
    root, output = root.resolve(), output.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Archive directory not found: {root}")
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Export and archive directories must not overlap.")
    if output.exists():
        raise FileExistsError("Export directory already exists; choose a new --output directory.")
    require_settled_archive(root)
    manifest = ArchiveManifestStore(root).load()
    catalog = read_catalog(root)

    # Record that this is a derived view, not a canonical backup or a complete site crawl.
    output.mkdir(parents=True)
    summary = {
        "export_schema_version": 1,
        "format": "wikidot-readable-export",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "incomplete",
        "site": manifest.site.model_dump(mode="json"),
        "pages": [],
        "standalone_threads": [],
        "warnings": list(catalog.warnings) if catalog else [],
    }
    _write_json(output / "export.json", summary)
    if catalog:
        atomic_write(
            output / "forum-catalog.json", catalog.model_dump_json(indent=2).encode("utf-8")
        )

    # Page records determine current discussion links; reverse links can retain older references.
    pages = []
    for metadata in sorted((root / "pages").glob("*/page.json")):
        page = PageRecord.model_validate_json(
            archive_path(root, metadata.relative_to(root).as_posix()).read_bytes()
        )
        if page.page_id <= 0 or metadata.parent.name != str(page.page_id):
            raise ValueError(f"Page ownership mismatch: {metadata}")
        pages.append(page)

    used_page_names: set[str] = set()
    linked_threads: set[int] = set()
    for page in sorted(pages, key=lambda page: (page.fullname.casefold(), page.page_id)):
        if report:
            report(f"Exporting page: {page.fullname}")
        folder = export_name(page.fullname, identifier=page.page_id, used=used_page_names)
        relative = f"pages/{folder}"
        target = output / relative
        page_dir = archive_path(root, f"pages/{page.page_id}")
        warnings: list[str] = []
        target.mkdir(parents=True)
        source_copied = _copy_checked(
            archive_path(page_dir, page.source.path),
            target / "source.txt",
            page.source.sha256,
            warnings,
            "Current source",
        )
        metadata = page.model_copy(deep=True)
        metadata.source.path = "source.txt"
        atomic_write(target / "page.json", metadata.model_dump_json(indent=2).encode("utf-8"))
        attachments = _export_files(root, page_dir, target, page.page_id, warnings)
        revision_count = _export_revisions(page_dir, target, page.page_id, warnings)

        items = [link("page.json", "Page metadata")]
        if source_copied:
            atomic_write(
                target / "source.html",
                source_html(
                    (target / "source.txt").read_bytes().decode("utf-8"),
                    title=f"Source: {page.fullname}",
                    text_path="source.txt",
                    back_path="index.html",
                ),
            )
            items.append(link("source.html", "Original Wikidot source"))
        if (target / "files.json").exists():
            items.append(link("files.json", "Attachment metadata and filename mapping"))
        if (target / "revisions/index.html").exists():
            items.append(link("revisions/index.html", f"Revision history ({revision_count})"))
        if page.discussion_thread_id is not None:
            thread_id = page.discussion_thread_id
            if archive_path(root, f"forums/threads/{thread_id}/thread.json").is_file():
                _export_discussion(
                    root,
                    thread_id,
                    target / "discussion",
                    manifest.site.url,
                    warnings,
                    back_path="../index.html",
                )
                linked_threads.add(thread_id)
                items.append(link("discussion/index.html", "Page discussion"))
            else:
                warnings.append(f"Discussion thread {thread_id} is not archived.")

        _write_json(target / "export-status.json", {"page_id": page.page_id, "warnings": warnings})
        body = "<p>" + link("../../index.html", "All pages and forums") + "</p>"
        body += "<p>Source is original wiki markup, not a rendered copy of the Wikidot page.</p>"
        body += "".join(f'<p class="warning">{escape(warning)}</p>' for warning in warnings)
        body += "<ul>" + "".join(f"<li>{item}</li>" for item in items + attachments) + "</ul>"
        atomic_write(target / "index.html", document(page.title or page.fullname, body))
        summary["pages"].append(
            {
                "page_id": page.page_id,
                "fullname": page.fullname,
                "path": relative,
                "discussion_thread_id": page.discussion_thread_id,
                "warnings": warnings,
            }
        )

    # Threads without an exported page must remain browsable in their own right.
    used_thread_names: set[str] = set()
    for path in sorted((root / "forums/threads").glob("*/thread.json")):
        thread_id = int(path.parent.name)
        if path.parent.name != str(thread_id) or thread_id <= 0:
            raise ValueError(f"Invalid thread directory: {path.parent}")
        if thread_id in linked_threads:
            continue
        archive_path(root, path.relative_to(root).as_posix())
        thread, _, _ = read_thread(root, thread_id)
        folder = export_name(
            thread.title or f"untitled-{thread_id}", identifier=thread_id, used=used_thread_names
        )
        relative = f"forums/{folder}"
        warnings = []
        if report:
            report(f"Exporting standalone thread: {thread_id}")
        title = _export_discussion(
            root,
            thread_id,
            output / relative,
            manifest.site.url,
            warnings,
            back_path="../../index.html",
        )
        summary["standalone_threads"].append(
            {
                "thread_id": thread_id,
                "title": title,
                "path": relative,
                "warnings": warnings,
            }
        )

    entries = summary["pages"] + summary["standalone_threads"]
    warning_count = len(summary["warnings"]) + sum(len(entry["warnings"]) for entry in entries)
    summary["status"] = "completed_with_warnings" if warning_count else "completed"
    summary["warning_count"] = warning_count
    body = (
        "<p>Offline export of archived content. This does not certify site-wide completeness.</p>"
    )
    body += f"<p>{warning_count} warning(s). " + link("export.json", "Export report") + "</p>"
    for heading, group in [
        ("Pages", summary["pages"]),
        ("Forum threads not linked to an exported page", summary["standalone_threads"]),
    ]:
        body += f"<h2>{heading}</h2><ul>"
        for entry in group:
            label = entry.get("fullname", entry.get("title", ""))
            body += "<li>" + link(entry["path"] + "/index.html", label)
            body += f" ({len(entry['warnings'])} warning(s))</li>"
        body += "</ul>"
    atomic_write(
        output / "index.html", document(manifest.site.title or manifest.site.unix_name, body)
    )
    _write_json(output / "export.json", summary)
    return summary
