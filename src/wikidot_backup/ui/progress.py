"""Rich-based terminal progress reporting."""

from __future__ import annotations

from types import TracebackType

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


class RichBackupProgress:
    """Display site backup progress using Rich.

    The progress count represents pages whose processing attempt has
    finished. Merely starting a page does not advance the counter, which
    prevents interrupted pages from appearing completed.
    """

    def __init__(self) -> None:
        """Create the Rich progress display."""

        self._progress = Progress(
            SpinnerColumn(),

            TextColumn(
                "[bold blue]{task.description}"
            ),

            BarColumn(),

            MofNCompleteColumn(),

            TextColumn(
                "• [cyan]{task.fields[current_page]}"
            ),

            TextColumn(
                "• [green]{task.fields[saved]} saved"
            ),

            TextColumn(
                "• [red]{task.fields[failed]} failed"
            ),

            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )

        self._task_id: TaskID | None = None

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
        self._progress.console.print(
            "[cyan]Fetching page list...[/cyan]"
        )

    def begin(
        self,
        *,
        discovered: int,
        already_completed: int,
        pending: int,
    ) -> None:
        """Initialize a progress task for the current backup run."""

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
            f"[red]Failed page:[/red] {fullname} "
            f"({type(exception).__name__}: {exception})"
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

    def _require_task(self) -> TaskID:
        """Return the active task ID or fail on incorrect reporter usage."""

        if self._task_id is None:
            raise RuntimeError(
                "RichBackupProgress.begin() must be called first."
            )

        return self._task_id
