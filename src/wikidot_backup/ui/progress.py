"""Rich-based terminal progress reporting."""

from __future__ import annotations

from types import TracebackType

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from wikidot_backup.services.backup_types import ForumProgressEvent


class RichBackupProgress:
    """Display site backup progress using Rich.

    The progress count represents pages whose processing attempt has
    finished. Merely starting a page does not advance the counter, which
    prevents interrupted pages from appearing completed.
    """

    def __init__(self, *, console: Console | None = None, verbose: bool = False) -> None:
        """Create the Rich progress display."""

        self._progress = Progress(
            SpinnerColumn(),

            TextColumn(
                "[bold blue]{task.description}"
            ),

            BarColumn(),

            MofNCompleteColumn(),

            TextColumn(
                "• {task.fields[current_page]}", markup=False,
            ),

            TextColumn(
                "• [green]{task.fields[saved]} saved"
            ),

            TextColumn(
                "• [red]{task.fields[failed]} failed"
            ),

            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )

        self._task_id: TaskID | None = None
        self._verbose = verbose
        self._forum_phase: str | None = None
        self._validation_fullname: str | None = None

    def __enter__(self) -> RichBackupProgress:
        """Start rendering the Rich progress display."""

        self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop rendering even when the backup is interrupted."""

        self._progress.stop()

    def discovery_started(self) -> None:
        """Report that Wikidot page discovery has started."""
        self._start_preparation("Fetching page list", total=None)

    def discovery_advanced(self, discovered: int) -> None:
        """Update after each ListPages response, rather than leaving a static message."""
        self._progress.update(
            self._require_task(), completed=discovered, current_page=f"{discovered} found",
        )

    def resume_loading(self) -> None:
        """Show when the local completion journal is being read."""
        self._progress.stop()
        if self._task_id is not None:
            self._progress.remove_task(self._task_id)
            self._task_id = None
        self._progress.console.print("Reading resume state...", markup=False, highlight=False)

    def resume_validation(self, *, total: int, completed: int, fullname: str) -> None:
        """Keep the current network lookup visible, including while waiting for retries."""
        if not fullname:
            self._start_preparation("Checking saved page IDs", total=total)
            self._validation_fullname = None
        self._progress.update(
            self._require_task(), completed=completed,
            current_page="done" if completed == total else fullname or "starting",
        )
        if fullname and fullname != self._validation_fullname:
            if self._verbose:
                self._progress.console.print(
                    f"Checking saved page ID: {fullname}", markup=False, highlight=False,
                )
            self._validation_fullname = fullname

    def _start_preparation(self, description: str, *, total: int | None) -> None:
        """Replace the previous phase so its counters cannot look stuck."""
        self._progress.stop()
        if self._task_id is not None:
            self._progress.remove_task(self._task_id)
        self._task_id = self._progress.add_task(
            description, total=total, current_page="waiting", saved=0, failed=0,
        )
        self._progress.start()

    def begin(
        self,
        *,
        discovered: int,
        already_completed: int,
        pending: int,
    ) -> None:
        """Initialize a progress task for the current backup run."""

        self._progress.stop()
        if self._task_id is not None:
            self._progress.remove_task(self._task_id)
        self._progress.console.print(
            f"Discovered: [bold]{discovered}[/bold]  "
            f"Already completed: [bold]{already_completed}[/bold]  "
            f"Processing: [bold]{pending}[/bold]"
        )

        self._task_id = self._progress.add_task(
            "Pages",
            total=pending,
            current_page="-",
            saved=0,
            failed=0,
        )
        self._progress.start()

    def page_started(
        self,
        *,
        fullname: str,
    ) -> None:
        """Show which page is currently being processed.

        The completed counter is deliberately not advanced here.
        """

        task_id = self._require_task()

        self._progress.update(
            task_id,
            current_page=fullname,
        )

    def page_succeeded(
        self,
        *,
        fullname: str,
        saved: int,
        failed: int,
    ) -> None:
        """Advance progress after a page has been safely archived."""

        task_id = self._require_task()

        self._progress.update(
            task_id,
            advance=1,
            current_page=fullname,
            saved=saved,
            failed=failed,
        )
        if self._verbose:
            self._progress.console.print(f"Saved page: {fullname}", markup=False, highlight=False)

    def page_failed(
        self,
        *,
        fullname: str,
        exception: Exception,
        saved: int,
        failed: int,
    ) -> None:
        """Advance progress and display a failed page."""

        task_id = self._require_task()

        # console.print integrates with the live progress display without
        # corrupting the progress bar output.
        self._progress.console.print(
            f"Failed page: {fullname} "
            f"({type(exception).__name__}: {exception})", markup=False, highlight=False,
        )

        self._progress.update(
            task_id,
            advance=1,
            current_page=fullname,
            saved=saved,
            failed=failed,
        )

    def end(
        self,
        *,
        saved: int,
        failed: int,
    ) -> None:
        """Update final counters after collection finishes."""

        task_id = self._require_task()

        self._progress.update(
            task_id,
            current_page="done",
            saved=saved,
            failed=failed,
        )
        self._progress.stop()

    def forum_event(self, event: ForumProgressEvent) -> None:
        """Render each forum phase through the same console and live display."""
        if event.phase != self._forum_phase:
            self._progress.stop()
            if self._task_id is not None:
                self._progress.remove_task(self._task_id)
            self._forum_phase = event.phase
            self._task_id = self._progress.add_task(
                "Forum categories" if event.phase == "categories" else "Threads",
                total=event.total, current_page="fetching", saved=0, failed=0,
            )
            self._progress.start()

        finished = event.total is not None and event.completed == event.total
        self._progress.update(
            self._require_task(), total=event.total, completed=event.completed,
            current_page="done" if finished else event.item or "fetching",
            saved=event.saved, failed=event.failed,
        )
        if self._verbose and event.message:
            self._progress.console.print(event.message, markup=False, highlight=False)

    def _require_task(self) -> TaskID:
        """Return the active task ID or fail on incorrect reporter usage."""

        if self._task_id is None:
            raise RuntimeError(
                "RichBackupProgress.begin() must be called first."
            )

        return self._task_id
