"""Site-wide Wikidot backup orchestration."""
from __future__ import annotations

from pathlib import Path

from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.services.backup_types import BackupProgressReporter, SiteBackupResult
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.indexes import rebuild_page_indexes
from wikidot_backup.storage.state import BackupState
from wikidot_backup.wikidot.client import WikidotClient


def backup_site(
        client: WikidotClient,
        output: Path,
        *,
        limit: int | None = None,
        progress: BackupProgressReporter | None = None,
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

        limit:
            Optional maximum number of unfinished pages to process during
            this invocation. Primarily useful during development.

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

    writer = ArchiveWriter(output)
    state = BackupState(output)

    if progress is not None:
        progress.discovery_started()

    # Enumeration must succeed completely before any page collection begins.
    # Otherwise a partial page list could be mistaken for a full-site backup.
    fullnames = client.list_page_fullnames()

    discovered_count = len(fullnames)

    completed = state.load_completed_pages()

    pending_all = [
        fullname
        for fullname in fullnames
        if fullname not in completed
    ]

    already_completed_count = (
            discovered_count - len(pending_all)
    )

    if limit is None:
        pending = pending_all
    else:
        pending = pending_all[:limit]

    # A supplied limit does not necessarily mean the run is incomplete.
    # For example, limit=20 with only 8 pending pages still finishes the site.
    limited_run = len(pending) < len(pending_all)

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

        try:
            page, source = collect_page(
                client,
                fullname,
            )

            writer.save_page(
                page,
                source,
            )

            # Mark the page completed only after all archive files have
            # been written successfully.
            state.record_completed(
                fullname=page.fullname,
                page_id=page.page_id,
            )

        except Exception as exc:
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

    resume_state_cleared = False

    if not limited_run and failed == 0:
        state.clear_completed_pages()
        resume_state_cleared = True

    if progress is not None:
        progress.end(
            saved=saved,
            failed=failed,
        )

    return SiteBackupResult(
        discovered=discovered_count,
        already_completed=already_completed_count,
        processed=saved + failed,
        saved=saved,
        failed=failed,
        limited=limited_run,
        resume_state_cleared=resume_state_cleared,
    )
