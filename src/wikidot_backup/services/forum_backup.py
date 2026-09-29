"""Site forum and archived page-discussion orchestration."""
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from wikidot_backup.collectors.forum_threads import collect_thread
from wikidot_backup.models.forum_records import ForumCategoryRecord, ForumDiscoveryRecord
from wikidot_backup.models.manifest import ArchiveSite
from wikidot_backup.models.page import PageRecord
from wikidot_backup.services.backup_types import ForumBackupResult, ForumProgressEvent
from wikidot_backup.storage.atomic import atomic_write, recover_archive_writes
from wikidot_backup.storage.forum_archive import (
    ForumState,
    read_thread,
    write_catalog,
    write_thread,
)
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.errors import PAGE_COLLECTION_ERRORS


def backup_forums(
    client: WikidotClient,
    output: Path,
    *,
    revisions: bool = False,
    limit: int | None = None,
    refresh: bool = False,
    report: Callable[[ForumProgressEvent], None] | None = None,
    finalize: bool = True,
) -> ForumBackupResult:
    """Discover all categories, union local discussion IDs, then archive threads.

    --limit restricts unfinished threads, not discovery. Count discrepancies keep
    resume state and prevent a successful-run marker. --refresh starts a new
    crawl without removing any canonical forum data.

    A combined site backup passes finalize=False so it can commit success and
    clear both resume files only after all requested components have succeeded.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    # Archive identity and recovery
    site = client.site_data
    manifest = ArchiveManifestStore(output)
    manifest.ensure_archive(
        ArchiveSite(
            id=site.id,
            unix_name=site.unix_name,
            title=site.title,
            domain=site.domain,
            url=site.url,
        )
    )

    recover_archive_writes(output)
    state = ForumState(output)
    if refresh:
        state.clear()

    # Discovery and catalog snapshot
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}"
    result = ForumBackupResult()
    forum = client.forums
    if report:
        report(ForumProgressEvent("categories", None))
    categories, groups, index_html = forum.catalog()
    if report:
        report(ForumProgressEvent("categories", len(categories)))
    category_records = []
    thread_ids = set()

    for category_index, category in enumerate(categories):
        if report:
            report(ForumProgressEvent(
                "categories", len(categories), category_index, item=category.title,
            ))

        ids = forum.category_threads(category.id)
        thread_ids.update(ids)
        if len(ids) != category.reported_threads:
            result.warnings.append(
                f"Category {category.id}: Wikidot reports {category.reported_threads} threads; "
                f"its listing returned {len(ids)}."
            )

        category_records.append(
            ForumCategoryRecord(
                category_id=category.id,
                group_position=category.group_position,
                title=category.title,
                description_html=category.description_html,
                reported_threads=category.reported_threads,
                discovered_thread_ids=ids,
            )
        )
        if report:
            report(ForumProgressEvent(
                "categories", len(categories), category_index + 1, item=category.title,
                message=f"Discovered category {category.id}: {category.title}",
            ))

    references = _load_discussion_references(output)
    thread_ids.update(references)
    discovery = ForumDiscoveryRecord(
        run_id=run_id,
        fetched_at=datetime.now(UTC),
        groups_html=groups,
        categories=category_records,
        index_html=index_html,
        page_discussion_thread_ids=sorted(references),
        warnings=result.warnings,
    )

    # The current view and its historical snapshot always publish together.
    write_catalog(output, discovery)
    # Thread collection and durable completion state
    errors: list[str] = []
    pending_thread_ids = []
    for thread_id in sorted(thread_ids):
        completed = state.completed.get(thread_id)
        if completed and (completed.revisions or not revisions):
            archived, _, _ = read_thread(output, thread_id)
            if completed.revisions and not archived.revisions_included:
                raise RuntimeError("Forum resume state disagrees with archive")

            # New local page references require a fresh thread record.
            if set(references.get(thread_id, [])) <= set(archived.archived_page_ids):
                result.skipped += 1
                continue

        pending_thread_ids.append(thread_id)

    selected_thread_ids = pending_thread_ids if limit is None else pending_thread_ids[:limit]
    if report:
        report(ForumProgressEvent("threads", len(selected_thread_ids)))

    for processed, thread_id in enumerate(selected_thread_ids):
        if report:
            report(ForumProgressEvent(
                "threads", len(selected_thread_ids), processed,
                result.saved, result.failed, item=str(thread_id),
            ))
        try:
            thread, posts, history = collect_thread(
                forum,
                thread_id,
                page_ids=references.get(thread_id, []),
                revisions=revisions,
            )
            write_thread(output, thread, posts, history)
            if thread.reported_posts != len(posts):
                result.warnings.append(
                    f"Thread {thread_id}: Wikidot reports {thread.reported_posts} posts; "
                    f"retrieved {len(posts)}. Thread remains pending."
                )
                # Do not reuse a previously completed state after a discrepant refresh.
                state.completed.pop(thread_id, None)
                state.flush()
            else:
                state.save(thread_id, revisions=revisions)

            result.saved += 1
            message = f"Saved thread {thread_id}: {thread.title}"
        except PAGE_COLLECTION_ERRORS as exc:
            result.failed += 1
            errors.append(f"Thread {thread_id}: {exc}")
            message = f"Failed thread {thread_id}: {exc}"
            atomic_write(
                output / ".state" / "forum-errors.jsonl",
                (
                    "".join(
                        json.dumps({"error": error}, ensure_ascii=False) + "\n" for error in errors
                    )
                ).encode("utf-8"),
            )
        if report:
            report(ForumProgressEvent(
                "threads", len(selected_thread_ids), processed + 1,
                result.saved, result.failed, item=str(thread_id), message=message,
            ))

    # Keep each run's report, including failures and partial discovery evidence.
    atomic_write(
        output / "forums" / "runs" / run_id / "report.json",
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "catalog": "catalog.json",
                "finished_at": datetime.now(UTC).isoformat(),
                "limited": limit is not None,
                "revisions_requested": revisions,
                "saved": result.saved,
                "skipped": result.skipped,
                "errors": errors,
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
    )

    if finalize and not result.failed and not result.warnings:
        manifest.record_success(
            components=["forums", "forum_revisions"] if revisions else ["forums"],
            full_backup=False,
        )
        if limit is None:
            state.clear()

    return result


def _load_discussion_references(output: Path) -> dict[int, list[int]]:
    """Group archived page IDs by their shared discussion thread."""
    references: dict[int, list[int]] = {}

    for metadata_path in sorted((output / "pages").glob("*/page.json")):
        page = PageRecord.model_validate_json(metadata_path.read_bytes())
        if metadata_path.parent.name != str(page.page_id):
            raise RuntimeError(f"Page identity mismatch: {metadata_path}")

        if page.discussion_thread_id is not None:
            references.setdefault(page.discussion_thread_id, []).append(page.page_id)

    return references
