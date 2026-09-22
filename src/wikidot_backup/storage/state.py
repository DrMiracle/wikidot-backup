"""Temporary state used to resume interrupted backup runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wikidot_backup.config import TEXT_ENCODING, TEXT_NEWLINE
from wikidot_backup.services.backup_types import BackupComponent


@dataclass(slots=True)
class PageBackupState:
    """Resume information accumulated for one Wikidot page."""

    page_id: int | None = None
    completed_components: set[BackupComponent] = field(default_factory=set)


class BackupState:
    """Manage resumable state for an in-progress site backup.

    Completed pages are recorded only after their archive files have been
    successfully written. If the process is interrupted, a later invocation
    can therefore skip pages that were already safely archived.

    This state is temporary. Once a complete site crawl finishes without
    errors, the completed-page state is removed so a future backup run can
    inspect the site again.
    """

    def __init__(self, archive_root: Path) -> None:
        """Initialize state storage inside an archive directory.

        Args:
            archive_root:
                Root directory of the backup archive.
        """

        self.state_dir = archive_root / ".state"

        self.completed_path = self.state_dir / "resume.jsonl"

        self.errors_path = self.state_dir / "errors.jsonl"

    def load_page_states(self) -> dict[str, PageBackupState]:
        """Return completed backup components grouped by page fullname.

        Multiple JSONL records for the same page are merged. This allows
        components to be completed across separate resumed invocations.

        Returns:
            Mapping from page fullname to the set of components that have been
            safely persisted.

        Raises:
            RuntimeError:
                If resume state contains malformed or unsupported records.
        """
        return load_page_states(self.completed_path)

    def start_run(self) -> None:
        """Clear this attempt's errors while preserving component resume records."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.errors_path.write_text("", encoding=TEXT_ENCODING, newline=TEXT_NEWLINE)

    def record_component_completed(
        self,
        *,
        fullname: str,
        page_id: int,
        component: BackupComponent,
    ) -> None:
        """Record a component only after all its required data is persisted."""
        self._append_json_line(
            self.completed_path,
            {
                "fullname": fullname,
                "page_id": page_id,
                "component": component.value,
                "completed_at": self._utc_now(),
            },
        )

    def record_error(self, *, fullname: str, exception: Exception) -> None:
        """Record an expected remote collection failure for the current attempt."""
        self._append_json_line(
            self.errors_path,
            {
                "fullname": fullname,
                "error_type": type(exception).__name__,
                "message": str(exception),
                "failed_at": self._utc_now(),
            },
        )

    def clear_resume_state(self) -> None:
        """Remove resume state after a successful unlimited crawl."""
        self.completed_path.unlink(missing_ok=True)

    @staticmethod
    def _utc_now() -> str:
        """Return a timezone-aware UTC timestamp suitable for JSON."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _append_json_line(path: Path, record: dict[str, Any]) -> None:
        """Append one JSON object to a UTF-8 JSONL file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding=TEXT_ENCODING, newline=TEXT_NEWLINE) as file:
            file.write(json.dumps(record, ensure_ascii=False) + TEXT_NEWLINE)


def load_page_states(path: Path) -> dict[str, PageBackupState]:
    """Read and validate legacy/current resume records without modifying the archive."""
    if not path.exists():
        return {}

    states: dict[str, PageBackupState] = {}

    with path.open("r", encoding=TEXT_ENCODING) as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid resume state in {path} at line {line_number}."
                ) from exc

            if not isinstance(record, dict):
                raise RuntimeError(f"Invalid resume record in {path} at line {line_number}.")
            fullname = record.get("fullname")
            page_id = record.get("page_id")
            component_raw = record.get("component")

            if not isinstance(fullname, str) or not fullname:
                raise RuntimeError(f"Invalid fullname in {path} at line {line_number}.")

            if type(page_id) is not int or page_id < 1:
                raise RuntimeError(f"Invalid page ID in {path} at line {line_number}.")

            # Older resume records predate component tracking. Such records
            # represented successful archival of the current page itself.
            if "component" not in record:
                component = BackupComponent.PAGE
            else:
                try:
                    component = BackupComponent(component_raw)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"Invalid backup component in "
                        f"{path} "
                        f"at line {line_number}: "
                        f"{component_raw!r}."
                    ) from exc

            page_state = states.setdefault(
                fullname,
                PageBackupState(),
            )

            # A fullname should not refer to different page IDs within one
            # resumable backup state. Treat that as inconsistent state rather
            # than silently combining records from different pages.
            if page_state.page_id is not None and page_state.page_id != page_id:
                raise RuntimeError(
                    f"Conflicting page IDs for {fullname!r} in {path} at line {line_number}."
                )

            page_state.page_id = page_id
            page_state.completed_components.add(component)

    return states
