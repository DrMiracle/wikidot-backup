"""Site-wide Wikidot backup orchestration."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wikidot_backup.collectors.files import collect_page_files
from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.collectors.revisions import collect_page_revisions
from wikidot_backup.models.manifest import ArchiveSite
from wikidot_backup.services.backup_types import (
    BackupComponent,
    BackupOptions,
    BackupProgressReporter,
    ForumProgressEvent,
    SiteBackupResult,
)
from wikidot_backup.services.forum_backup import backup_forums
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.atomic import recover_archive_writes
from wikidot_backup.storage.forum_archive import ForumState
from wikidot_backup.storage.indexes import rebuild_page_indexes
from wikidot_backup.storage.manifest import ArchiveManifestStore
from wikidot_backup.storage.state import BackupState, PageBackupState
from wikidot_backup.wikidot.client import WikidotClient
from wikidot_backup.wikidot.errors import PAGE_COLLECTION_ERRORS, WikidotResourceError


def backup_site(
        client: WikidotClient,
        output: Path,
        *,
        options: BackupOptions,
        limit: int | None = None,
        progress: BackupProgressReporter | None = None,
        forum_report: Callable[[ForumProgressEvent], None] | None = None,
) -> SiteBackupResult:
    """Archive current versions of pages from an entire Wikidot site.

    The site is enumerated before collection starts. Successfully written
    pages are recorded in temporary resume state so interrupted runs can
    continue without downloading completed pages again.

    A page is marked as completed only after its metadata and source have
    been successfully written to the archive.

    Args:
        client:
            Connected Wikidot client.

        output:
            Root directory of the filesystem archive.

        options:
            Components to include in the backup. Current page metadata and
            source are always included; optional components such as revision
            history are included according to these settings.

        limit:
            Maximum number of pages to process during this invocation.
            ``None`` processes all pages that are incomplete for the
            requested backup components.

        progress:
            Optional progress reporter. The collector itself is independent
            of any specific terminal/UI library.

    Returns:
        Summary describing the completed backup invocation.

    Raises:
        Exceptions raised during initial site enumeration are propagated.
        Continuing after incomplete enumeration could create a misleadingly
        incomplete backup.
    """

    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    writer = ArchiveWriter(output)
    state = BackupState(output)
    manifest_store = ArchiveManifestStore(output)

    site = client.site_data

    manifest_store.ensure_archive(
        ArchiveSite(
            id=site.id,
            unix_name=site.unix_name,
            title=site.title,
            domain=site.domain,
            url=site.url,
        )
    )
    recover_archive_writes(output)

    if progress is not None:
        progress.discovery_started()

    # Enumeration must succeed completely before any page collection begins.
    # Otherwise a partial page list could be mistaken for a full-site backup.
    fullnames = client.list_page_fullnames()
    discovered_count = len(fullnames)

    page_states = state.load_page_states()
    required_components = options.required_components

    # A reused fullname must not hide a replacement page behind completed state.
    for fullname in fullnames:
        completed = page_states.get(fullname)
        if _is_page_complete(completed, required_components):
            assert completed is not None and completed.page_id is not None
            client.validate_page_identity(fullname, completed.page_id)

    pending_all = [
        fullname
        for fullname in fullnames
        if not _is_page_complete(
            page_states.get(fullname),
            required_components,
        )
    ]

    already_completed_count = (
            discovered_count - len(pending_all)
    )

    if limit is None:
        pending = pending_all
    else:
        pending = pending_all[:limit]

    # Only an explicitly unlimited run finalizes the resumable crawl.
    limited_run = limit is not None

    state.start_run()

    if progress is not None:
        progress.begin(
            discovered=discovered_count,
            already_completed=already_completed_count,
            pending=len(pending),
        )

    saved = 0
    failed = 0

    for fullname in pending:
        if progress is not None:
            # Starting a page does NOT advance the progress counter.
            progress.page_started(
                fullname=fullname,
            )

        page_state = page_states.setdefault(
            fullname,
            PageBackupState(),
        )

        try:
            if page_state.page_id is not None:
                client.validate_page_identity(fullname, page_state.page_id)
            if BackupComponent.PAGE not in page_state.completed_components:
                page, source = collect_page(
                    client,
                    fullname,
                )
                if page.fullname != fullname or (
                    page_state.page_id is not None and page_state.page_id != page.page_id
                ):
                    raise WikidotResourceError(f"Wikidot page identity changed: {fullname}")

                writer.save_page(
                    page,
                    source,
                )

                # Mark the page completed only after all archive files have
                # been written successfully.
                state.record_component_completed(
                    fullname=page.fullname,
                    page_id=page.page_id,
                    component=BackupComponent.PAGE,
                )

                page_state.page_id = page.page_id
                page_state.completed_components.add(
                    BackupComponent.PAGE
                )

            if (
                options.include_files
                and BackupComponent.FILES not in page_state.completed_components
            ):
                if page_state.page_id is None:
                    raise RuntimeError(
                        f"Cannot archive files for {fullname!r}: "
                        "page ID is unavailable."
                    )

                files = collect_page_files(
                    client,
                    page_id=page_state.page_id,
                    fullname=fullname,
                )

                writer.save_page_files(
                    page_state.page_id,
                    files,
                )

                state.record_component_completed(
                    fullname=fullname,
                    page_id=page_state.page_id,
                    component=BackupComponent.FILES,
                )

                page_state.completed_components.add(
                    BackupComponent.FILES
                )

            if (
                options.include_revisions
                and BackupComponent.REVISIONS not in page_state.completed_components
            ):
                if page_state.page_id is None:
                    raise RuntimeError(
                        f"Cannot archive revisions for {fullname!r}: "
                        "page ID is unavailable."
                    )

                revisions = collect_page_revisions(
                    client,
                    page_id=page_state.page_id,
                    fullname=fullname,
                )

                writer.save_page_revisions(
                    page_state.page_id,
                    revisions,
                )

                state.record_component_completed(
                    fullname=fullname,
                    page_id=page_state.page_id,
                    component=BackupComponent.REVISIONS,
                )

                page_state.completed_components.add(
                    BackupComponent.REVISIONS
                )

        except PAGE_COLLECTION_ERRORS as exc:
            failed += 1

            state.record_error(
                fullname=fullname,
                exception=exc,
            )

            if progress is not None:
                # A failed page still counts as processed during this run.
                progress.page_failed(
                    fullname=fullname,
                    exception=exc,
                    saved=saved,
                    failed=failed,
                )

            continue

        saved += 1

        if progress is not None:
            progress.page_succeeded(
                fullname=fullname,
                saved=saved,
                failed=failed,
            )

    # Indexes are derived from all page records currently present in the archive,
    # including pages completed during earlier resumed runs.
    rebuild_page_indexes(output)

    if progress is not None:
        progress.end(saved=saved, failed=failed)

    # Forums share site-level success, but use thread-level resume state.
    forum_result = None
    if options.include_forums:
        forum_result = backup_forums(
            client, output, revisions=options.include_revisions, limit=limit,
            report=forum_report, finalize=False,
        )

    forums_succeeded = forum_result is None or (
        forum_result.failed == 0 and not forum_result.warnings
    )
    resume_state_cleared = False
    if failed == 0 and forums_succeeded:
        components = [component.value for component in options.required_components]
        if options.include_forums:
            components.append("forums")
            if options.include_revisions:
                components.append("forum_revisions")

        manifest_store.record_success(
            components=components,
            full_backup=not limited_run,
        )

        if not limited_run:
            state.clear_resume_state()
            if options.include_forums:
                ForumState(output).clear()
            resume_state_cleared = True

    return SiteBackupResult(
        discovered=discovered_count,
        already_completed=already_completed_count,
        processed=saved + failed,
        saved=saved,
        failed=failed,
        limited=limited_run,
        resume_state_cleared=resume_state_cleared,
        forums=forum_result,
    )


def _is_page_complete(
    page_state: PageBackupState | None,
    required_components: frozenset[BackupComponent],
) -> bool:
    """Return whether all requested components are already complete."""
    if page_state is None:
        return False

    return required_components.issubset(
        page_state.completed_components
    )
