"""Types defining the public contract of backup services."""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ForumProgressEvent:
    """Structured forum progress, independent of terminal rendering."""

    phase: Literal["categories", "threads"]
    total: int | None
    completed: int = 0
    saved: int = 0
    failed: int = 0
    item: str = ""
    message: str | None = None


@dataclass(slots=True)
class ForumBackupResult:
    """Fetched forum content and discovery coverage reported separately."""

    saved: int = 0
    skipped: int = 0
    failed: int = 0
    warnings: list[str] = field(default_factory=list)


class BackupComponent(StrEnum):
    """Independently trackable component of an archived Wikidot page."""

    PAGE = "page"
    REVISIONS = "revisions"
    FILES = "files"

@dataclass(frozen=True, slots=True)
class BackupOptions:
    """Components requested for a site backup."""

    include_revisions: bool = False
    include_files: bool = True
    include_forums: bool = False

    @property
    def required_components(self) -> frozenset[BackupComponent]:
        """Return components that must be completed for this backup."""
        components = {
            BackupComponent.PAGE,
        }

        if self.include_revisions:
            components.add(
                BackupComponent.REVISIONS
            )

        if self.include_files:
            components.add(
                BackupComponent.FILES
            )

        return frozenset(components)

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
    forums: ForumBackupResult | None = None


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

    def discovery_started(self) -> None:
        """Report that Wikidot page discovery has started."""
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
