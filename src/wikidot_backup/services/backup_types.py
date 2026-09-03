"""Types defining the public contract of backup services."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SiteBackupResult:
    """Summary of one site backup invocation."""

    discovered: int
    already_completed: int
    processed: int
    saved: int
    failed: int
    limited: bool
    resume_state_cleared: bool


# Contract for structural subtyping of RichBackupProgress!
class BackupProgressReporter(Protocol):
    """Receive progress events from a site backup operation."""

    def begin(
            self,
            *,
            discovered: int,
            already_completed: int,
            pending: int,
    ) -> None:
        """Initialize progress reporting for a backup run."""
        ...

    def page_started(
            self,
            *,
            fullname: str,
    ) -> None:
        """Report that collection of one page has started."""
        ...

    def page_succeeded(
            self,
            *,
            fullname: str,
            saved: int,
            failed: int,
    ) -> None:
        """Report that one page was successfully archived."""
        ...

    def page_failed(
            self,
            *,
            fullname: str,
            exception: Exception,
            saved: int,
            failed: int,
    ) -> None:
        """Report that one page could not be archived."""
        ...

    def end(
            self,
            *,
            saved: int,
            failed: int,
    ) -> None:
        """Report that the current backup invocation has finished."""
        ...
