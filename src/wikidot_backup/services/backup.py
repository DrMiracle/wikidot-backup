"""Site-wide Wikidot backup orchestration."""
from __future__ import annotations

from pathlib import Path

from wikidot_backup.collectors.files import collect_page_files
from wikidot_backup.collectors.pages import collect_page
from wikidot_backup.collectors.revisions import collect_page_revisions
from wikidot_backup.services.backup_types import (
    BackupProgressReporter,
    SiteBackupResult,
    BackupOptions,
    BackupComponent
)
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.storage.indexes import rebuild_page_indexes
from wikidot_backup.storage.state import BackupState, PageBackupState
from wikidot_backup.wikidot.client import WikidotClient


def backup_site(
        client: WikidotClient,
        output: Path,
        *,
        options: BackupOptions,
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

    writer = ArchiveWriter(output)
    state = BackupState(output)

    if progress is not None:
        progress.discovery_started()

    # Enumeration must succeed completely before any page collection begins.
    # Otherwise a partial page list could be mistaken for a full-site backup.
    fullnames = client.list_page_fullnames()
    discovered_count = len(fullnames)

    page_states = state.load_page_states()
    required_components = options.required_components

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

        page_state = page_states.setdefault(
            fullname,
            PageBackupState(),
        )

        try:
            if BackupComponent.PAGE not in page_state.completed_components:
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
                state.record_component_completed(
                    fullname=page.fullname,
                    page_id=page.page_id,
                    component=BackupComponent.PAGE,
                )

                page_state.page_id = page.page_id
                page_state.completed_components.add(
                    BackupComponent.PAGE
                )

            if options.include_files and BackupComponent.FILES not in page_state.completed_components:
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

            if options.include_revisions and BackupComponent.REVISIONS not in page_state.completed_components:
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
    # TODO: implement archive state as a source of truth so that we don't fetch already completed page
    if not limited_run and failed == 0:
        state.clear_resume_state()
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
