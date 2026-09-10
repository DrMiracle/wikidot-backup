"""Tests for archive filesystem inspection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import wikidot_backup.storage.inspection as inspection


def test_inspect_archive_counts_stored_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Inspection should report data physically present in the archive."""
    page_dir = tmp_path / "pages" / "123"
    page_dir.mkdir(
        parents=True
    )

    (page_dir / "page.json").write_text(
        "{}",
        encoding="utf-8",
    )

    (page_dir / "source.txt").write_text(
        "page source",
        encoding="utf-8",
    )

    (page_dir / "files.json").write_text(
        "{}",
        encoding="utf-8",
    )

    revisions_dir = (
        page_dir / "revisions"
    )
    revisions_dir.mkdir()

    (
        revisions_dir / "revisions.jsonl"
    ).write_text(
        '{"revision_no": 0}\n'
        '{"revision_no": 1}\n',
        encoding="utf-8",
    )

    blobs_dir = (
        tmp_path / "blobs" / "sha256"
    )
    blobs_dir.mkdir(
        parents=True
    )

    (blobs_dir / "abc").write_bytes(
        b"first"
    )
    (blobs_dir / "def").write_bytes(
        b"second"
    )

    state_dir = tmp_path / ".state"
    state_dir.mkdir()

    # One page can have several completed component records, but should
    # count only once as a page represented in resume state.
    (
        state_dir / "resume.jsonl"
    ).write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "fullname": "test-page",
                        "component": "page",
                    }
                ),
                json.dumps(
                    {
                        "fullname": "test-page",
                        "component": "files",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (
        state_dir / "errors.jsonl"
    ).write_text(
        '{"fullname": "broken"}\n',
        encoding="utf-8",
    )

    class FakePageRecord:
        """Minimal page model used by the inspection test."""

        @staticmethod
        def model_validate_json(_data: str):
            return SimpleNamespace(
                source=SimpleNamespace(
                    path="source.txt"
                )
            )

    class FakePageFilesRecord:
        """Minimal attachment collection used by the inspection test."""

        @staticmethod
        def model_validate_json(_data: str):
            return SimpleNamespace(
                files=[
                    object(),
                    object(),
                    object(),
                ]
            )

    monkeypatch.setattr(
        inspection,
        "PageRecord",
        FakePageRecord,
    )
    monkeypatch.setattr(
        inspection,
        "PageFilesRecord",
        FakePageFilesRecord,
    )

    result = inspection.inspect_archive(
        tmp_path
    )

    assert result.pages == 1
    assert result.current_sources == 1

    assert result.pages_with_file_metadata == 1
    assert result.file_records == 3
    assert result.unique_blobs == 2

    assert result.pages_with_revisions == 1
    assert result.revisions == 2

    assert result.resume_present is True
    assert result.resume_pages == 1
    assert result.error_records == 1

    assert result.total_bytes > 0

def test_inspect_archive_handles_missing_optional_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Missing optional components should be reported as zero."""
    page_dir = tmp_path / "pages" / "123"
    page_dir.mkdir(
        parents=True
    )

    (page_dir / "page.json").write_text(
        "{}",
        encoding="utf-8",
    )

    class FakePageRecord:
        @staticmethod
        def model_validate_json(_data: str):
            return SimpleNamespace(
                source=SimpleNamespace(
                    path="source.txt"
                )
            )

    monkeypatch.setattr(
        inspection,
        "PageRecord",
        FakePageRecord,
    )

    result = inspection.inspect_archive(
        tmp_path
    )

    assert result.pages == 1
    assert result.current_sources == 0

    assert result.pages_with_file_metadata == 0
    assert result.file_records == 0
    assert result.unique_blobs == 0

    assert result.pages_with_revisions == 0
    assert result.revisions == 0

    assert result.resume_present is False
    assert result.resume_pages == 0
    assert result.error_records == 0
