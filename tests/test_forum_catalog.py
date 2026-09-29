"""Current forum catalogs and their per-run historical snapshots."""

import json

import pytest

from wikidot_backup.models.forum_records import ForumDiscoveryRecord
from wikidot_backup.storage.forum_archive import read_catalog, write_catalog


def catalog(run_id, title="Example"):
    return ForumDiscoveryRecord(
        run_id=run_id, fetched_at="2026-09-28T12:00:00Z", groups_html=[title],
        categories=[], index_html="", page_discussion_thread_ids=[], warnings=[],
    )


def test_current_catalog_and_history(tmp_path):
    write_catalog(tmp_path, catalog("first"))
    snapshot = tmp_path / "forums/runs/first/catalog.json"
    original = snapshot.read_bytes()
    write_catalog(tmp_path, catalog("second", "Changed"))

    assert read_catalog(tmp_path).run_id == "second"
    assert snapshot.read_bytes() == original
    assert (tmp_path / "forums/catalog.json").read_bytes() == (
        tmp_path / "forums/runs/second/catalog.json"
    ).read_bytes()


def test_legacy_catalog_remains_readable_and_untouched(tmp_path):
    legacy = tmp_path / "forums/catalogs/old-uuid.json"
    legacy.parent.mkdir(parents=True)
    data = catalog(None).model_dump(mode="json")
    data.pop("run_id")
    legacy.write_text(json.dumps(data), encoding="utf-8")
    original = legacy.read_bytes()

    assert read_catalog(tmp_path).run_id is None
    write_catalog(tmp_path, catalog("new"))
    assert read_catalog(tmp_path).run_id == "new"
    assert legacy.read_bytes() == original


def test_failed_publication_restores_current_catalog(tmp_path, monkeypatch):
    from pathlib import Path

    write_catalog(tmp_path, catalog("first"))
    original_replace = Path.replace

    def fail_current(path, destination):
        if path.suffix == ".new" and Path(destination) == tmp_path / "forums/catalog.json":
            raise OSError("Publication failed")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_current)
    with pytest.raises(OSError, match="Publication failed"):
        write_catalog(tmp_path, catalog("second"))

    assert read_catalog(tmp_path).run_id == "first"
    assert not (tmp_path / "forums/runs/second/catalog.json").exists()
