"""Temporary state used to resume interrupted backup runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wikidot_backup.config import TEXT_ENCODING, TEXT_NEWLINE


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

        self.completed_path = (
            self.state_dir / "completed_pages.jsonl"
        )

        self.errors_path = (
            self.state_dir / "errors.jsonl"
        )

        self.state_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load_completed_pages(self) -> set[str]:
        """Return fullnames successfully completed by an earlier attempt.

        Invalid or incomplete JSONL records are treated as corruption and
        raise an exception rather than silently producing an incomplete
        backup.

        Returns:
            Set of completed Wikidot page fullnames.
        """

        if not self.completed_path.exists():
            return set()

        completed: set[str] = set()

        with self.completed_path.open("r", encoding=TEXT_ENCODING) as file:
            for line_number, line in enumerate(file, start=1):
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Invalid resume state in "
                        f"{self.completed_path} "
                        f"at line {line_number}."
                    ) from exc

                fullname = record.get("fullname")

                if not isinstance(fullname, str):
                    raise RuntimeError(
                        "Invalid completed-page record in "
                        f"{self.completed_path} "
                        f"at line {line_number}."
                    )

                completed.add(fullname)

        return completed

    def start_run(self) -> None:
        """Start a new backup attempt.

        The error log represents only the current attempt, so it is cleared
        when a run starts. Completed-page state is intentionally preserved
        because it is required for resume.
        """

        self.errors_path.write_text(
            "",
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        )

    def record_completed(
        self,
        *,
        fullname: str,
        page_id: int,
    ) -> None:
        """Record a page as safely archived.

        This method must be called only after both page metadata and source
        have been successfully written.

        Args:
            fullname:
                Canonical Wikidot page fullname.

            page_id:
                Numeric Wikidot page ID.
        """

        self._append_json_line(
            self.completed_path,
            {
                "fullname": fullname,
                "page_id": page_id,
                "completed_at": self._utc_now(),
            },
        )

    def record_error(
        self,
        *,
        fullname: str,
        exception: Exception,
    ) -> None:
        """Record a page collection failure for the current run.

        Args:
            fullname:
                Wikidot page fullname that could not be archived.

            exception:
                Exception raised while collecting or writing the page.
        """

        self._append_json_line(
            self.errors_path,
            {
                "fullname": fullname,
                "error_type": type(exception).__name__,
                "message": str(exception),
                "failed_at": self._utc_now(),
            },
        )

    def clear_completed_pages(self) -> None:
        """Remove temporary resume state after a complete successful crawl."""

        if self.completed_path.exists():
            self.completed_path.unlink()

    @staticmethod
    def _utc_now() -> str:
        """Return a timezone-aware UTC timestamp suitable for JSON."""

        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _append_json_line(
        path: Path,
        record: dict[str, Any],
    ) -> None:
        """Append one JSON object to a UTF-8 JSONL file."""

        serialized = json.dumps(
            record,
            ensure_ascii=False,
        )

        with path.open(
            "a",
            encoding=TEXT_ENCODING,
            newline=TEXT_NEWLINE,
        ) as file:
            file.write(serialized)
            file.write(TEXT_NEWLINE)
