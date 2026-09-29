"""Recoverable thread publication, strict readers, and independent resume state."""

from pathlib import Path

from pydantic import BaseModel

from wikidot_backup.models.forum_records import (
    ForumDiscoveryRecord,
    ForumPostRecord,
    ForumResumeRecord,
    ForumRevisionRecord,
    ForumThreadRecord,
)
from wikidot_backup.storage.atomic import ArchiveTransaction, atomic_write


def read_catalog(root: Path) -> ForumDiscoveryRecord | None:
    """Read the current catalog, falling back to snapshots from older archives."""
    current = root / "forums" / "catalog.json"
    if current.exists():
        return ForumDiscoveryRecord.model_validate_json(current.read_bytes())

    snapshots = [
        ForumDiscoveryRecord.model_validate_json(path.read_bytes())
        for path in (root / "forums" / "catalogs").glob("*.json")
    ]
    return max(snapshots, key=lambda snapshot: snapshot.fetched_at, default=None)


def write_catalog(root: Path, discovery: ForumDiscoveryRecord) -> None:
    """Publish a current view together with its immutable per-run snapshot."""
    if discovery.run_id is None:
        raise ValueError("A new forum catalog must identify its run")
    # Validate existing metadata before replacing its current view.
    read_catalog(root)
    snapshot_path = f"forums/runs/{discovery.run_id}/catalog.json"
    if (root / snapshot_path).exists():
        raise FileExistsError(f"Forum catalog snapshot already exists: {snapshot_path}")

    content = discovery.model_dump_json(indent=2).encode("utf-8")
    with ArchiveTransaction(root) as transaction:
        transaction.stage(snapshot_path, content)
        transaction.stage("forums/catalog.json", content)
        transaction.commit()


def read_records[Record: BaseModel](path: Path, model: type[Record]) -> list[Record]:
    """Read strict JSONL records; malformed lines are never skipped."""
    if not path.exists():
        return []

    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def json_lines(records: list[BaseModel]) -> bytes:
    """Serialize portable UTF-8 JSONL with a final newline."""
    return "".join(record.model_dump_json() + "\n" for record in records).encode("utf-8")


def read_thread(
    root: Path, thread_id: int
) -> tuple[
    ForumThreadRecord,
    list[ForumPostRecord],
    list[ForumRevisionRecord],
]:
    """Validate ownership and current snapshot membership before reuse or inspection."""
    directory = root / "forums" / "threads" / str(thread_id)
    thread = ForumThreadRecord.model_validate_json((directory / "thread.json").read_bytes())
    if not (directory / "posts.jsonl").is_file():
        raise RuntimeError("Missing forum posts file")

    posts = read_records(directory / "posts.jsonl", ForumPostRecord)
    history = read_records(directory / "post-revisions.jsonl", ForumRevisionRecord)

    # Validate ownership before comparing the snapshot's record sets.
    if thread.thread_id != thread_id or any(
        record.thread_id != thread_id for record in [*posts, *history]
    ):
        raise RuntimeError("Forum archive ownership mismatch")
    post_ids = {post.post_id for post in posts}
    revision_ids = {revision.revision_id for revision in history}
    observed_post_ids = set(thread.observed_post_ids)
    posts_with_history = {revision.post_id for revision in history}

    if len(post_ids) != len(posts) or len(revision_ids) != len(history):
        raise RuntimeError("Duplicate forum archive records")

    if len(observed_post_ids) != len(thread.observed_post_ids):
        raise RuntimeError("Duplicate observed forum post IDs")

    if not observed_post_ids <= post_ids or not posts_with_history <= post_ids:
        raise RuntimeError("Missing forum post metadata")

    if thread.revisions_included and not observed_post_ids <= posts_with_history:
        raise RuntimeError("Missing forum revision history")

    return thread, posts, history


def write_thread(
    root: Path,
    thread: ForumThreadRecord,
    posts: list[ForumPostRecord],
    history: list[ForumRevisionRecord],
) -> None:
    """Replace observed records while retaining records absent from a later snapshot."""
    relative = f"forums/threads/{thread.thread_id}"
    old_posts, old_history = [], []

    if (root / relative / "thread.json").exists():
        old_thread, old_posts, old_history = read_thread(root, thread.thread_id)
        thread.archived_page_ids = sorted(
            set(old_thread.archived_page_ids + thread.archived_page_ids)
        )

    # Keep records missing from the latest remote snapshot for recoverability.
    merged_posts = {post.post_id: post for post in old_posts}
    merged_posts.update({post.post_id: post for post in posts})
    merged_history = {revision.revision_id: revision for revision in old_history}
    merged_history.update({revision.revision_id: revision for revision in history})

    with ArchiveTransaction(root) as transaction:
        transaction.stage(
            f"{relative}/thread.json", thread.model_dump_json(indent=2).encode("utf-8")
        )
        transaction.stage(f"{relative}/posts.jsonl", json_lines(list(merged_posts.values())))

        if thread.revisions_included or old_history:
            transaction.stage(
                f"{relative}/post-revisions.jsonl", json_lines(list(merged_history.values()))
            )

        transaction.commit()


class ForumState:
    """Atomic thread-level completion, independent of page-scoped components."""

    def __init__(self, root: Path) -> None:
        self.path = root / ".state" / "forum-resume.jsonl"
        records = read_records(self.path, ForumResumeRecord)
        self.completed = {record.thread_id: record for record in records}
        if len(self.completed) != len(records):
            raise RuntimeError("Duplicate forum resume records")

    def save(self, thread_id: int, *, revisions: bool) -> None:
        self.completed[thread_id] = ForumResumeRecord(thread_id=thread_id, revisions=revisions)
        self.flush()

    def flush(self) -> None:
        """Publish the full state atomically, including removal of stale completions."""
        atomic_write(self.path, json_lines(list(self.completed.values())))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.completed.clear()
