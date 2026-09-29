"""Page revision metadata has a stable order independent of remote enumeration."""

import json

import pytest

from wikidot_backup.models.common import SourceRef
from wikidot_backup.models.revision import PageRevisionRecord
from wikidot_backup.storage.archive import ArchiveWriter
from wikidot_backup.util.hashing import sha256_text


@pytest.mark.parametrize("order", [(2, 1, 0), (0, 1, 2), (1, 2, 0)])
def test_revision_metadata_is_oldest_first_without_changing_sources(tmp_path, order):
    # IDs deliberately differ from revision order: revision_no defines chronology.
    revision_ids = [900, 700, 800]
    pairs = []
    for number in order:
        revision_id = revision_ids[number]
        source = f"Revision {number}\n\n  preserved indentation\n"
        record = PageRevisionRecord(
            page_id=123, revision_id=revision_id, revision_no=number,
            source=SourceRef(
                path=f"revisions/sources/{revision_id}.txt",
                sha256=sha256_text(source), characters=len(source),
            ),
        )
        pairs.append((record, source))

    count = ArchiveWriter(tmp_path).save_page_revisions(123, iter(pairs))

    page_dir = tmp_path / "pages/123"
    records = [json.loads(line) for line in (
        page_dir / "revisions/revisions.jsonl"
    ).read_text(encoding="utf-8").splitlines()]
    assert count == 3
    assert [record["revision_no"] for record in records] == [0, 1, 2]
    assert [record["revision_id"] for record in records] == revision_ids
    for record, source in pairs:
        assert (page_dir / record.source.path).read_bytes() == source.encode("utf-8")
